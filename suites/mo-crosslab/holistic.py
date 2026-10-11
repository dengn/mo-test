"""100 long thirty-source customer→demand→cash→carbon→CVaR procurement plans."""
import concurrent.futures,json,time,traceback
import numpy as np,pandas as pd
from scipy.optimize import linprog
from data import ROOT,tables,local_oracle,connect
from audit import snapshot
from graphs import query,params
from models import calculate
from pandas_graphs import build
from common import compare,equal,receipt

def bridge_sql(i):
    p=params(i)
    return f'''WITH cash AS (SELECT oid,SUM(paid) cash FROM payments WHERE success=1 AND day<{p['end']} GROUP BY oid),
    returned AS (SELECT oid,SUM(refunded) refund FROM refunds WHERE day<{p['end']} GROUP BY oid),
    linked AS (SELECT o.cid,i.pid,i.qty,(COALESCE(c.cash,0)-COALESCE(r.refund,0))*i.qty*i.price/o.amount net_value
    FROM orders o JOIN items i ON o.oid=i.oid JOIN products pr ON i.pid=pr.pid JOIN customers cu ON o.cid=cu.cid
    LEFT JOIN cash c ON o.oid=c.oid LEFT JOIN returned r ON o.oid=r.oid
    WHERE o.cancelled=0 AND o.day BETWEEN {p['start']} AND {p['end']}-1 AND cu.cid>={p['lo']} AND cu.cid<{p['hi']})
    SELECT cid,pid,SUM(qty) units,SUM(net_value) net_value FROM linked GROUP BY cid,pid ORDER BY cid,pid'''

def bridge_pandas(source,i):
    p=params(i);start=p['start'];end=p['end'];lo=p['lo'];hi=p['hi']
    o=source['orders'].query('cancelled==0 and @start<=day<@end and @lo<=cid<@hi')
    x=source['items'].merge(o,on='oid',how='inner',validate='many_to_one')
    cash=source['payments'].query('success==1 and day<@end').groupby('oid').paid.sum()
    ret=source['refunds'].query('day<@end').groupby('oid').refunded.sum()
    x['net_value']=(x.oid.map(cash).fillna(0)-x.oid.map(ret).fillna(0))*x.qty*x.price/x.amount
    return x.groupby(['cid','pid']).agg(units=('qty','sum'),net_value=('net_value','sum')).reset_index().sort_values(['cid','pid']).reset_index(drop=True)

def decide(customer,product,bridge,i):
    p=params(i);customer=customer.astype(float).round(8);product=product.astype(float).round(8);bridge=bridge.astype(float).round(8)
    risk=calculate(2,customer,i);forecast=calculate(10,product,i)
    cids=customer.cid.to_numpy(int);pids=product.pid.to_numpy(int)
    # Native pandas pivot/reindex protects the customer×product grain from sparse purchases.
    weights=bridge.pivot(index='cid',columns='pid',values='units').reindex(index=cids,columns=pids).fillna(0).to_numpy(float)
    totals=weights.sum(0);normalized=weights/np.maximum(totals[None,:],1)
    probability=np.array([r[1] for r in risk['decisions']]);credit_risk=np.einsum('cp,c->p',normalized,probability)
    credit_risk=np.where(totals>0,credit_risk,probability.mean())
    daily=np.maximum(1,np.array([r[1] for r in forecast['decisions']]))
    # Known synthetic stockout mechanism supplies a transparent censoring correction.
    daily/=np.maximum(.2,1-.8*product.stockout_rate.to_numpy())
    feature=product[['macro_return','fill_rate','delay','vibration','downtime','energy_cost']].to_numpy(float)
    z=(feature-feature.mean(0))/np.maximum(feature.std(0),.001);u,s,v=np.linalg.svd(z,full_matrices=False)
    factor=u[:,:4]*s[:4];factor/=np.maximum(np.sqrt((factor**2).sum(1,keepdims=True)),1)
    rng=np.random.default_rng(p['seed']+999999);scenarios=128;horizon=14
    common=rng.normal(size=(scenarios,horizon,4));idio=rng.normal(size=(scenarios,horizon,len(pids)))
    correlated=np.einsum('sdf,pf->sdp',common,factor)*.45+idio*np.sqrt(1-.45**2)
    demand=np.maximum(0,daily[None,None,:]*(1+.12*correlated));total_demand=demand.sum(1)
    supply_shock=np.clip(product.fill_rate.to_numpy()[None,:]-.04*common[:,0,0,None],.3,1)
    unit_gain=(product.price.to_numpy()-product.unit_cost.to_numpy())[None,:]*supply_shock*(1-credit_risk[None,:])-.02*product.delay.to_numpy()[None,:]
    needed=np.maximum(0,np.quantile(total_demand,p['service'],axis=0)-product.on_hand.to_numpy())
    n=len(pids);category=product.category.to_numpy(int);unit_cost=product.unit_cost.to_numpy()
    budget=p['budget']*12+max(0,float(customer.margin.sum()))*.03
    energy_intensity=product.energy_cost.to_numpy()/np.maximum(product.output.to_numpy(),1)
    carbon_intensity=product.carbon.to_numpy()/np.maximum(product.output.to_numpy(),1)
    resources=[unit_cost,energy_intensity,carbon_intensity];caps=[budget,budget*.04,budget*.11];names=['procurement_cash','energy','carbon']
    for g in np.unique(category):
        row=(category==g).astype(float);plant=product.loc[product.category==g].iloc[0]
        resources.append(row);caps.append(float(plant.output)*horizon*.7);names.append('plant_'+str(g))
    resource=np.vstack(resources);rhs=np.array(caps)
    # CVaR loss epigraph: per-scenario losses, free VaR threshold and nonnegative excesses.
    risk_weight=p['risk']*2;alpha=.90;objective=np.r_[-unit_gain.mean(0),risk_weight,np.full(scenarios,risk_weight/((1-alpha)*scenarios))]
    constraints=np.zeros((len(rhs)+scenarios,n+1+scenarios));constraints[:len(rhs),:n]=resource
    constraints[len(rhs):,:n]=-unit_gain;constraints[len(rhs):,n]=-1;constraints[len(rhs):,n+1:]=-np.eye(scenarios)
    bounds=np.r_[rhs,np.zeros(scenarios)]
    result=linprog(objective,A_ub=constraints,b_ub=bounds,bounds=[(0,float(v)) for v in needed]+[(None,None)]+[(0,None)]*scenarios,method='highs')
    assert result.success,result.message
    units=np.floor(np.maximum(0,result.x[:n]));scenario_gain=unit_gain@units;loss=-scenario_gain;threshold=np.quantile(loss,alpha)
    cvar=threshold+np.maximum(loss-threshold,0).mean()/(1-alpha)
    usage=resource@units;cash_by_day=np.einsum('sdp,p->sd',demand,unit_cost)
    checks={'bridge_unique_grain':not bridge.duplicated(['cid','pid']).any(),'customer_weight_conservation':bool(np.allclose(normalized[:,totals>0].sum(0),1)),
        'credit_probability_bounds':bool(np.all((credit_risk>=0)&(credit_risk<=1))),
        'scenario_tensor_finite_nonnegative':bool(np.isfinite(demand).all() and np.all(demand>=0)),
        'procurement_integer_nonnegative':bool(np.all(units>=0) and np.all(units==np.floor(units))),
        'cash_carbon_energy_plant_constraints':bool(np.all(usage<=rhs+1e-6)),
        'continuous_cvar_epigraph_feasible':bool(np.all(constraints@result.x<=bounds+1e-5)),
        'cvar_at_least_mean_loss':bool(cvar>=loss.mean()-1e-6),
        'forecast_constraints':all(forecast['checks'].values()),'credit_constraints':all(risk['checks'].values())}
    return {'metrics':{'scenarios':scenarios,'horizon_days':horizon,'tensor_shape':list(demand.shape),'procurement_cash':float(usage[0]),'expected_gain':float(scenario_gain.mean()),'loss_cvar_90':float(cvar),'daily_cash_p95':np.quantile(cash_by_day,.95,axis=0).tolist(),'lp_variables':len(objective),'lp_constraints':len(bounds)},
        'checks':checks,'diagnostics':{'product_credit_risk':credit_risk.tolist(),'forecast_daily_demand':daily.tolist(),'resource_names':names,'resource_usage':usage.tolist(),'resource_caps':rhs.tolist(),'continuous_objective':float(result.fun),'scenario_gain':scenario_gain.tolist()},
        'decisions':np.column_stack([pids,units,unit_gain.mean(0)*units]).tolist()}

def main():
    source=snapshot('holistic');out=ROOT/'results/holistic';out.mkdir(parents=True,exist_ok=True);indices=list(map(int,np.linspace(0,499,100,dtype=int)));start=time.time();counts={}
    def worker(w,indices):
        o=local_oracle(tables());c=connect();rows=[];table=f'holistic_decisions_{w}'
        with c.cursor() as q:q.execute(f'CREATE TABLE IF NOT EXISTS {table}(case_id INT,entity DOUBLE,allocation DOUBLE,benefit DOUBLE)');q.execute(f'SELECT COUNT(*) FROM {table}');assert q.fetchone()[0]==0
        with (out/f'cases-{w}.jsonl').open('w') as file:
            for case,i in indices:
                t=time.time();sqls=[query('customer',i),query('product',i),bridge_sql(i)];r={'case_id':case,'parameter':i,'parameters':params(i),'requirement':'thirty_source_cvar_operating_plan','sql':sqls,'stages':[]}
                try:
                    e=[o.execute(sql).fetchdf() for sql in sqls];a=[]
                    for sql,expected in zip(sqls,e):
                        with c.cursor() as q:q.execute(sql);actual=pd.DataFrame(q.fetchall(),columns=[d[0] for d in q.description])
                        compare(expected,actual);a.append(actual);r['stages'].append({'expected':receipt(expected),'actual':receipt(actual)})
                    native=[build(source,'customer',i,e[0].columns),build(source,'product',i,e[1].columns),bridge_pandas(source,i)]
                    for expected,actual in zip(e,native):compare(expected,actual)
                    em=decide(*e,i);am=decide(*native,i);r.update(expected_analysis=em,actual_analysis=am)
                    assert equal(em,am) and all(em['checks'].values()) and all(am['checks'].values())
                    records=[(case,*x) for x in am['decisions']]
                    with c.cursor() as q:
                        q.execute('BEGIN');q.executemany(f'INSERT INTO {table} VALUES(%s,%s,%s,%s)',records);q.execute(f'SELECT entity,allocation,benefit FROM {table} WHERE case_id=%s ORDER BY entity',(case,));assert equal(em['decisions'],q.fetchall())
                        q.execute('COMMIT' if case%2==0 else 'ROLLBACK');q.execute(f'SELECT COUNT(*) FROM {table} WHERE case_id=%s',(case,));assert q.fetchone()[0]==(len(records) if case%2==0 else 0)
                        q.execute(f'DELETE FROM {table} WHERE case_id=%s',(case,))
                    r['status']='pass'
                except Exception as exc:
                    r.update(status='error',error=str(exc),traceback=traceback.format_exc());c.rollback()
                    with c.cursor() as q:q.execute(f'DELETE FROM {table} WHERE case_id=%s',(case,))
                r['seconds']=time.time()-t;rows.append(r);file.write(json.dumps(r,allow_nan=False)+'\n');file.flush()
                print('holistic',case,i,r['status'],r.get('error','')[:200],flush=True)
        c.close();o.close();return rows
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:rows=sum(list(pool.map(lambda v:worker(*v),[(w,list(enumerate(indices))[w::2]) for w in range(2)])),[])
    (out/'meta.json').write_text(json.dumps({'workflows':len(rows),'counts':{k:sum(r['status']==k for r in rows) for k in {r['status'] for r in rows}},'seconds':time.time()-start,'source_tables_union':30,'scope':'Customer/product fact graphs plus a transaction bridge; independent native pandas reconstructions; credit calibration→robust demand forecast→128×14×80 correlated tensor→credit/supply shocks→CVaR epigraph LP→integer procurement→cash/energy/carbon/plant constraints→transaction publication. Excluded from main 10000 and Spark 200.'},indent=2))
if __name__=='__main__':main()

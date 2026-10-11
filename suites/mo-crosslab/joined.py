"""50 single-SQL thirty-table customer/product feature stores and allocation plans."""
import argparse,concurrent.futures,json,time,traceback
import numpy as np,pandas as pd
from scipy.optimize import linprog
from data import ROOT,tables,local_oracle,connect
from graphs import query,params
from holistic import bridge_sql,bridge_pandas
from pandas_graphs import build
from audit import snapshot
from common import compare,equal,receipt

def sql(i,customer_columns,product_columns):
    c=query('customer',i).removesuffix(' ORDER BY cid');p=query('product',i).removesuffix(' ORDER BY pid');b=bridge_sql(i).removesuffix(' ORDER BY cid,pid')
    projection=['b.cid AS cid','b.pid AS pid','b.units AS bridge_units','b.net_value AS bridge_value']
    projection += [f'c.{k} AS c_{k}' for k in customer_columns if k!='cid']+[f'p.{k} AS p_{k}' for k in product_columns if k!='pid']
    return 'WITH customer_snapshot AS ('+c+'),\nproduct_snapshot AS ('+p+'),\npurchases AS ('+b+')\nSELECT '+','.join(projection)+' FROM purchases b JOIN customer_snapshot c ON b.cid=c.cid JOIN product_snapshot p ON b.pid=p.pid ORDER BY b.cid,b.pid'

def native(source,i,cc,pc,columns):
    c=build(source,'customer',i,cc).rename(columns={k:'c_'+k for k in cc if k!='cid'})
    p=build(source,'product',i,pc).rename(columns={k:'p_'+k for k in pc if k!='pid'})
    b=bridge_pandas(source,i).rename(columns={'units':'bridge_units','net_value':'bridge_value'})
    return b.merge(c,on='cid',validate='many_to_one').merge(p,on='pid',validate='many_to_one')[list(columns)].sort_values(['cid','pid']).reset_index(drop=True)

def model(frame,i):
    p=params(i);a=frame.astype(float).round(8);ids=(a.cid.to_numpy(int)*100+a.pid.to_numpy(int))
    cols=['c_credit','c_recency','c_margin','c_earned','c_tickets','c_csat','c_dpd','c_overdue','c_balance','c_depth','p_demand','p_demand_variance','p_fill_rate','p_delay','p_on_hand','p_energy_cost','p_carbon','p_vibration','p_stockout_rate','p_macro_return']
    x=a[cols].to_numpy(float);z=np.clip((x-np.median(x,0))/np.maximum(np.median(abs(x-np.median(x,0)),0)*1.4826,.001),-8,8)
    cov=np.cov(z,rowvar=False);ev,vec=np.linalg.eigh(cov);latent=z@vec[:,-6:]
    # Independently check a pandas cross-domain exposure pivot with NumPy indexed accumulation.
    pivot=a.pivot_table(index='c_region',columns='p_category',values='bridge_value',aggfunc='sum',fill_value=0)
    target=np.zeros(pivot.shape);ri={v:k for k,v in enumerate(pivot.index)};ci={v:k for k,v in enumerate(pivot.columns)}
    np.add.at(target,([ri[v] for v in a.c_region],[ci[v] for v in a.p_category]),a.bridge_value.to_numpy())
    share=a.bridge_units/a.groupby('cid').bridge_units.transform('sum')
    score=np.maximum(0,a.c_margin.to_numpy())*share.to_numpy()*(.3+.7*a.p_fill_rate.to_numpy())
    credit_loss=np.clip(a.c_dpd.to_numpy()/180+a.c_overdue.to_numpy()/np.maximum(a.c_balance.to_numpy(),1)*.05,0,.8)
    value=score*(1-credit_loss);cost=10+a.bridge_units.to_numpy()*a.p_unit_cost.to_numpy()*.08
    carbon=a.bridge_units.to_numpy()*a.p_carbon.to_numpy()/np.maximum(a.p_output.to_numpy(),1)
    resource=np.vstack([cost,carbon,np.ones(len(a))]);caps=np.array([p['budget'],p['budget']*.4,float(p['capacity'])*3])
    result=linprog(-value,A_ub=resource,b_ub=caps,bounds=(0,1),method='highs');assert result.success,result.message
    allocation=result.x;benefit=allocation*value
    checks={'customer_product_unique_grain':not a.duplicated(['cid','pid']).any(),'pandas_numpy_exposure_pivot':bool(np.allclose(pivot.to_numpy(),target,rtol=1e-12,atol=1e-8)),
        'customer_exposure_conservation':bool(np.allclose(share.groupby(a.cid).sum(),1)),
        'latent_covariance_psd':bool(ev.min()>-1e-8),'latent_basis_orthogonal':bool(np.allclose(vec[:,-6:].T@vec[:,-6:],np.eye(6))),
        'cash_carbon_capacity_constraints':bool(np.all(resource@allocation<=caps+1e-6)),
        'allocation_bounds':bool(np.all((allocation>=-1e-8)&(allocation<=1+1e-8)))}
    return {'metrics':{'pairs':len(a),'customers':int(a.cid.nunique()),'products':int(a.pid.nunique()),'profit_objective':float(benefit.sum()),'cash_spend':float(allocation@cost),'carbon_usage':float(allocation@carbon),'pca_explained_top6':float(ev[-6:].sum()/max(ev.sum(),1e-12))},
        'diagnostics':{'eigenvalues':ev.tolist(),'cross_region_category_value':pivot.to_numpy().tolist(),'resource_usage':(resource@allocation).tolist(),'resource_caps':caps.tolist()},'checks':checks,'decisions':np.column_stack([ids,allocation,benefit]).tolist()}

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--pilot',action='store_true');args=ap.parse_args();source=snapshot('joined');out=ROOT/'results'/('joined-pilot' if args.pilot else 'joined');out.mkdir(parents=True,exist_ok=True)
    indices=[0,249,499] if args.pilot else list(map(int,np.linspace(0,499,50,dtype=int)));started=time.time()
    def worker(w,indices):
        o=local_oracle(tables());c=connect();rows=[];cc=list(o.execute(query('customer',0)).fetchdf());pc=list(o.execute(query('product',0)).fetchdf());table=f'joined_decisions_{w}'
        with c.cursor() as q:q.execute(f'CREATE TABLE IF NOT EXISTS {table}(case_id INT,entity DOUBLE,allocation DOUBLE,benefit DOUBLE)');q.execute(f'SELECT COUNT(*) FROM {table}');assert q.fetchone()[0]==0
        with (out/f'cases-{w}.jsonl').open('w') as file:
            for case,i in indices:
                statement=sql(i,cc,pc);r={'case_id':case,'parameter':i,'parameters':params(i),'requirement':'thirty_table_single_sql_feature_store','sql':statement};t=time.time()
                try:
                    e=o.execute(statement).fetchdf()
                    with c.cursor() as q:q.execute(statement);a=pd.DataFrame(q.fetchall(),columns=[v[0] for v in q.description])
                    compare(e,a);n=native(source,i,cc,pc,e.columns);compare(e,n);compare(a,n);r.update(expected_facts=receipt(e),actual_facts=receipt(a),native_pandas_facts=receipt(n))
                    em=model(e,i);am=model(n,i);r.update(expected_analysis=em,actual_analysis=am);assert equal(em,am) and all(em['checks'].values()) and all(am['checks'].values())
                    with c.cursor() as q:
                        q.execute('BEGIN');q.executemany(f'INSERT INTO {table} VALUES(%s,%s,%s,%s)',[(case,*v) for v in am['decisions']]);q.execute(f'SELECT entity,allocation,benefit FROM {table} WHERE case_id=%s ORDER BY entity',(case,));assert equal(em['decisions'],q.fetchall());q.execute('COMMIT' if case%2==0 else 'ROLLBACK');q.execute(f'SELECT COUNT(*) FROM {table} WHERE case_id=%s',(case,));assert q.fetchone()[0]==(len(am['decisions']) if case%2==0 else 0);q.execute(f'DELETE FROM {table} WHERE case_id=%s',(case,))
                    r['status']='pass'
                except Exception as exc:
                    r.update(status='error',error=str(exc),traceback=traceback.format_exc());c.rollback()
                    with c.cursor() as q:q.execute(f'DELETE FROM {table} WHERE case_id=%s',(case,))
                r['seconds']=time.time()-t;rows.append(r);file.write(json.dumps(r,allow_nan=False)+'\n');file.flush();print('joined30',case,i,r['status'],r.get('error','')[:250],flush=True)
        c.close();o.close();return rows
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:rows=sum(list(pool.map(lambda z:worker(*z),[(w,list(enumerate(indices))[w::2]) for w in range(2)])),[])
    (out/'meta.json').write_text(json.dumps({'workflows':len(rows),'counts':{k:sum(r['status']==k for r in rows) for k in {r['status'] for r in rows}},'seconds':time.time()-started,'source_tables':30,'scope':'Single SQL with nested scoped CTEs for 30-source customer/product/purchase graph; independent native pandas reconstruction; robust PCA/exposure pivot and constrained resource allocation; transaction roundtrip. Separate from main/Spark/holistic counts.'},indent=2))
if __name__=='__main__':main()

import json
import numpy as np,pandas as pd
from data import ROOT,tables,connect,local_oracle,params
from scenarios import sql_for,SQL
from run import compare,plain

def main():
    data=tables();c=connect();checks={}
    for name,expected in data.items():
        with c.cursor() as q:
            q.execute(f'SELECT * FROM {name}');rows=q.fetchall()
        actual=pd.DataFrame(rows,columns=expected.columns)
        keys=list(expected.columns)
        for col in keys:
            if pd.api.types.is_datetime64_any_dtype(expected[col]):actual[col]=pd.to_datetime(actual[col])
        ex=expected.sort_values(keys,na_position='last').reset_index(drop=True)
        ac=actual.sort_values(keys,na_position='last').reset_index(drop=True)
        pd.testing.assert_frame_equal(ex,ac,check_dtype=False,rtol=1e-12,atol=1e-12)
        checks[name]={'rows':len(actual),'full_content':'pass'}
    db=local_oracle(data);cross=[];mapping={name:i for i,(name,_,_) in enumerate(SQL)}
    for i in range(0,1000,37):
        p=params(i);scope=data['customers']
        scope=scope[(scope.cid>=p['lo'])&(scope.cid<p['hi'])&(scope.region!=p['r'])]
        o=data['orders'];o=o[o.cid.isin(scope.cid)&(o.day>=p['d0'])&(o.day<p['d1'])]
        good=o[o.cancelled==0];group=o.groupby('cid');expected={}
        paid=data['payments'];paid=paid[paid.success==1].groupby('oid').paid.sum()
        v=o.amount.to_numpy()-o.oid.map(paid).fillna(0).to_numpy()
        expected['payment_coverage_anomaly']=[[len(o),int((v>1e-6).sum()),v.sum() if len(o) else None]]
        delta=good.sort_values(['cid','day','oid']).groupby('cid').day.diff().dropna().to_numpy()
        expected['repeat_purchase_intervals']=[[len(delta),delta.mean() if len(delta) else None,delta.var() if len(delta) else None,delta.max() if len(delta) else None]]
        prob=o.channel.value_counts().to_numpy()/len(o) if len(o) else np.array([])
        expected['empirical_entropy_of_channels']=[[len(prob),-(prob*np.log(prob)).sum() if len(prob) else None,(prob*prob).sum() if len(prob) else None]]
        x=group.size().to_numpy(dtype=float);y=group.amount.sum().to_numpy()
        slope=np.sum((x-x.mean())*(y-y.mean()))/np.sum((x-x.mean())**2) if len(x) and x.var()>0 else None
        expected['ols_regression_sufficient_stats']=[[len(x),slope,y.mean()-slope*x.mean() if slope is not None else None]]
        credit=scope.credit.fillna(scope.groupby('tier').credit.transform('mean')).to_numpy()
        expected['missing_credit_tier_imputation']=[[len(scope),int(scope.credit.notna().sum()),credit.sum(),credit.var()]]
        frequency=scope.cid.map(group.size()).fillna(0).to_numpy();avg=scope.cid.map(group.amount.mean()).fillna(0).to_numpy()
        pr=1/(1+np.exp(-(p['alpha']*frequency+avg/1000-scope.tier.to_numpy())))
        expected['logistic_probability_cross_features']=[[len(scope),pr.sum(),(pr*(1-pr)).sum(),int((pr>.5).sum())]]
        for name,ex in expected.items():
            actual=db.execute(sql_for(mapping[name],i)).fetchall()
            assert compare(ex,actual),(name,i,ex,actual)
            cross.append({'family':name,'parameter':i,'status':'pass'})
    c.close();db.close()
    (ROOT/'data-integrity.json').write_text(json.dumps(plain({'tables':checks,'numpy_pandas_cross_checks':cross,'cross_check_count':len(cross)}),indent=2))
    print('full data verified, independent checks',len(cross),flush=True)
if __name__=='__main__':main()

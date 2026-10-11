import json
import numpy as np,pandas as pd
from data import ROOT,tables,connect,local_oracle
from scenarios import BLOCKS,parameters
from run import equal,plain

def main():
 data=tables();c=connect();checks={}
 for name,expected in data.items():
  with c.cursor() as q:q.execute(f'SELECT * FROM {name}');rows=q.fetchall()
  actual=pd.DataFrame(rows,columns=expected.columns)
  for col in expected.columns:
   if pd.api.types.is_datetime64_any_dtype(expected[col]):actual[col]=pd.to_datetime(actual[col])
  keys=list(expected.columns)
  pd.testing.assert_frame_equal(expected.sort_values(keys,na_position='last').reset_index(drop=True),actual.sort_values(keys,na_position='last').reset_index(drop=True),check_dtype=False,rtol=1e-12,atol=1e-12)
  checks[name]={'rows':len(actual),'full_content':'pass'}
 c.close();db=local_oracle(data);cross=[]
 for i in [0,23,68,123,199]:
  p=parameters(i);cust=data['customers'];cust=cust[(cust.cid>=p['lo'])&(cust.cid<p['hi'])]
  base='WITH selected_customers AS (SELECT * FROM customers WHERE cid>={lo} AND cid<{hi}), '
  # Independently reproduce market rolling variance/drawdown and subscription backlog.
  market=data['market'].copy();market['ret']=np.log(market.close_price/market.groupby('asset').close_price.shift())
  market=market[(market.day>=p['m0'])&(market.day<=p['m1'])].copy();market['rv']=market.groupby('asset').ret.transform(lambda x:x.rolling(21,min_periods=1).var(ddof=0));market['drawdown']=market.close_price/market.groupby('asset').close_price.cummax()-1
  agg=market.groupby('asset').agg(growth=('ret','sum'),volatility=('rv','mean'),drawdown=('drawdown','min'))
  expected=[(int(r.cid),float(agg.loc[r.cid%8,'growth']*(r.credit if pd.notna(r.credit) else 0)),float(agg.loc[r.cid%8,'volatility']),float(agg.loc[r.cid%8,'drawdown'])) for r in cust.itertuples()]
  actual=db.execute((base+BLOCKS['market']+' SELECT cid,x,y,z FROM market_customer ORDER BY cid').format(**p)).fetchall();assert equal(expected,actual),(i,'market');cross.append({'parameter':i,'block':'market','rows':len(expected),'status':'pass'})
  subs=data['subscriptions'];subs=subs[subs.cid.isin(cust.cid)&(subs.month>=p['s0'])&(subs.month<=p['s1'])].copy();subs['arrears']=subs.billed-subs.paid;subs['backlog']=subs.groupby('cid').arrears.transform(lambda x:x.rolling(6,min_periods=1).sum());prev=subs.groupby('cid').active.shift();subs['reactivated']=((subs.active==1)&(prev==0)).astype(int)
  summary=subs.groupby('cid').agg(arrears=('arrears','sum'),backlog=('backlog','max'),retention=('active','mean'),reactivated=('reactivated','sum'));credit=cust.credit.fillna(cust.groupby('tier').credit.transform('mean'))
  expected=[(int(cid),float(summary.loc[cid,'arrears']/cr),float(summary.loc[cid,'backlog']),float(summary.loc[cid,'retention']+summary.loc[cid,'reactivated']/10)) for cid,cr in zip(cust.cid,credit)]
  actual=db.execute((base+BLOCKS['subscription']+' SELECT cid,x,y,z FROM subscription_customer ORDER BY cid').format(**p)).fetchall();assert equal(expected,actual),(i,'subscription');cross.append({'parameter':i,'block':'subscription','rows':len(expected),'status':'pass'})
 db.close();(ROOT/'data-integrity.json').write_text(json.dumps({'tables':checks,'independent_pandas_checks':cross},indent=2));print('14 full tables verified; independent block checks',len(cross))
if __name__=='__main__':main()

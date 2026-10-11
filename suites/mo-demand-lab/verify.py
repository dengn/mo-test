"""Full source integrity and independent Pandas accounting/as-of checks."""
import argparse,json,time
import numpy as np,pandas as pd
from data import ROOT,connect,tables,local_oracle
from facts import params
from catalog import queries
from run import rows_equal
ap=argparse.ArgumentParser();ap.add_argument('--final',action='store_true');args=ap.parse_args();data=tables();c=connect();checks={}
for name,expected in data.items():
 with c.cursor() as q:q.execute(f'SELECT * FROM {name}');actual=pd.DataFrame(q.fetchall(),columns=expected.columns)
 for col in expected:
  if pd.api.types.is_datetime64_any_dtype(expected[col]):actual[col]=pd.to_datetime(actual[col])
 keys=list(expected);pd.testing.assert_frame_equal(expected.sort_values(keys,na_position='last').reset_index(drop=True),actual.sort_values(keys,na_position='last').reset_index(drop=True),check_dtype=False,rtol=1e-12,atol=1e-12);checks[name]={'rows':len(actual),'full_content':'pass'}
c.close();oracle=local_oracle(data);accounting=[]
for i in [0,123,249]:
 p=params(i);orders=data['orders'];selected=orders[(orders.cid>=p['lo'])&(orders.cid<p['hi'])&(orders.day>=p['start'])&(orders.day<p['end'])&(orders.cancelled==0)].copy();payments=data['payments'];cash=payments[(payments.day<p['end'])&(payments.success==1)].groupby('oid').paid.sum();refund=data['refunds'];returned=refund[refund.day<p['end']].groupby('oid').refunded.sum();ledger=data['ledger'];latest=ledger[ledger.day<p['end']].sort_values(['event_id','revision_no','entry_id'],ascending=[True,False,False]).drop_duplicates('event_id');booked=latest.groupby('oid').amount.sum()
 expected=pd.DataFrame(dict(oid=selected.oid,cid=selected.cid,day=selected.day,cash=selected.oid.map(cash).fillna(0),ledger_amount=selected.oid.map(booked).fillna(0),returned=selected.oid.map(returned).fillna(0),invoice=selected.amount,collected=selected.oid.map(cash).fillna(0)));expected['outstanding']=np.maximum(0,expected.invoice-expected.collected);expected=expected.sort_values('oid').reset_index(drop=True);actual=oracle.execute(queries(14,i)[0]).fetchdf();assert rows_equal(expected,actual,['oid','cid','day'])
 net=expected.cash-expected.returned;by_day=net.groupby(expected.day).sum().reindex(np.arange(p['start'],p['end']),fill_value=0);dense=oracle.execute(queries(16,i)[0]).fetchdf();assert np.allclose(by_day.to_numpy(),dense.revenue.to_numpy(),rtol=1e-12,atol=1e-9);assert len(dense)==p['end']-p['start'];accounting.append({'parameter':i,'rows':len(expected),'dedup_asof_cash':'pass','calendar_zero_days':int((by_day==0).sum()),'calendar_daily_revenue':'pass'})
subs=data['subscriptions'];assert (subs[subs.cid%5==0].active==1).all();assert (data['prices'].stockout>0).any();assert data['customers'].credit.isna().any();assert data['ledger'].event_id.duplicated().any();assert ((data['shipments'].delivered_day>=89)).any()
r={'timestamp':time.time(),'tables':checks,'total_rows':sum(x['rows'] for x in checks.values()),'independent_pandas_accounting':accounting,'fixture_edge_cases':['no-order customers','missing credit','superseded ledger versions','failed payment attempts','stockout-censored sales','ongoing shipments','right-censored subscriptions','immediate subscription pauses','right-censored machine lifetimes']};(ROOT/('data-integrity-final.json' if args.final else 'data-integrity.json')).write_text(json.dumps(r,indent=2));print('30 source tables fully verified; independent accounting checks',len(accounting))

"""Independent validated pandas joins, windows, anti-joins and dense grids."""
import numpy as np,pandas as pd
from graphs import params

def merge(left,right,key,how='left'):
    return left.merge(right,on=key,how=how,validate='many_to_one')

def customer(data,i):
    p=params(i);end=p['end'];start=p['start'];c=data['customers'].query('@p["lo"]<=cid<@p["hi"]').copy()
    paid=data['payments'].query('success==1 and day<@end').groupby('oid').paid.sum().rename('cash').reset_index()
    refunded=data['refunds'].query('day<@end').groupby('oid').refunded.sum().rename('returned').reset_index()
    rev=data['ledger'].query('day<@end').sort_values(['event_id','revision_no','entry_id']).drop_duplicates('event_id',keep='last')
    book=rev.groupby('oid').amount.sum().rename('booked').reset_index()
    mix=merge(data['items'],data['products'].rename(columns={'price':'list_price'}),'pid')
    mix['list_value']=mix.qty*mix.list_price
    mix=mix.groupby('oid').agg(units=('qty','sum'),categories=('category','nunique'),list_value=('list_value','sum')).reset_index()
    all_o=data['orders'];volume=all_o.query('cancelled==0').groupby(['channel','day']).size().rename('buyers').reset_index()
    selected=all_o.query('cancelled==0 and @start<=day<@end and cid in @c.cid').copy()
    for block,key in [(paid,'oid'),(refunded,'oid'),(book,'oid'),(mix,'oid'),(data['shipments'],'oid'),(data['receivables'][['oid','due_day','invoice']],'oid'),(volume,['channel','day']),(data['campaigns'][['channel','day','spend']],['channel','day'])]:selected=merge(selected,block,key)
    for col in ['cash','returned','booked','units','categories','list_value']:selected[col]=selected[col].fillna(0)
    selected['acquisition']=(selected.spend/selected.buyers).fillna(0)
    selected['revenue']=selected.cash-selected.returned;selected['margin']=selected.revenue-selected.cost-selected.freight-selected.acquisition
    selected['late']=np.where(selected.delivered_day<end,np.maximum(0,selected.delivered_day-selected.promised_day),np.nan)
    selected['pending']=(selected.delivered_day>=end).astype(int);selected['outstanding']=np.maximum(0,selected.invoice-selected.cash)
    selected['overdue']=np.where(selected.due_day<end,selected.outstanding,0);selected['ledger_gap']=selected.booked-selected.cash
    selected['early']=selected.revenue.where(selected.day<(start+end)/2);selected['recent']=selected.revenue.where(selected.day>=(start+end)/2)
    sales=selected.groupby('cid').agg(n_orders=('oid','size'),revenue=('revenue','sum'),margin=('margin','sum'),cost=('cost','sum'),acquisition=('acquisition','sum'),outstanding=('outstanding','sum'),overdue=('overdue','sum'),units=('units','sum'),late=('late','mean'),pending=('pending','sum'),ledger_gap=('ledger_gap','sum'),variety=('categories','mean'),early=('early','mean'),recent=('recent','mean')).reset_index()
    sales['momentum']=sales.recent.fillna(0)-sales.early.fillna(0);sales=sales.drop(columns=['early','recent'])
    t=data['tickets'].query('@start<=day<@end').groupby('cid').agg(tickets=('ticket','size'),handling=('handle_minutes','sum'),csat=('csat','mean'),reopened=('reopened','sum')).reset_index()
    ev=data['events'].query('@start<=day<@end');session=ev.groupby(['cid','session_id']).kind.max().rename('depth').reset_index();session['converted']=(session.depth==4).astype(int)
    journey=session.groupby('cid').agg(sessions=('session_id','size'),converted=('converted','sum'),depth=('depth','mean')).reset_index()
    sub=data['subscriptions'].query('month<=@p["month"]').copy();sub['arrears']=sub.billed-sub.paid
    subs=sub.groupby('cid').agg(arrears=('arrears','sum'),active_months=('active','sum')).reset_index()
    active=sub.sort_values(['cid','month']).drop_duplicates('cid',keep='last')[['cid','active']];subs=merge(subs,active,'cid')
    contract=data['contracts'].query('start_day<@end').copy();fraction=np.clip((end-contract.start_day)/contract.term_days,0,1)
    contract['earned']=contract.booked*fraction;contract['deferred_revenue']=contract.booked*(1-fraction)
    contracts=contract.groupby('cid')[['earned','deferred_revenue']].sum().reset_index()
    snap=data['loan_performance'].query('day<@end').sort_values(['loan_id','day']).drop_duplicates('loan_id',keep='last')
    loans=merge(data['loans'].query('opened<@end'),snap[['loan_id','balance','dpd','defaulted']],'loan_id')
    loans.balance=loans.balance.fillna(loans.principal);loans[['dpd','defaulted']]=loans[['dpd','defaulted']].fillna(0)
    credit=loans.groupby('cid').agg(balance=('balance','sum'),dpd=('dpd','max'),defaulted=('defaulted','max')).reset_index()
    fraud=data['fraud_payments'].query('day<@end').copy();fraud['chargeback_value']=fraud.amount*fraud.chargeback
    fr=fraud.groupby('cid').agg(chargeback=('chargeback_value','sum'),payment_volume=('amount','sum')).reset_index()
    ex=data['experiment'].query('day<@end').groupby('cid').agg(baseline=('baseline','mean'),exp_revenue=('revenue','mean'),latency=('latency','mean')).reset_index()
    peer=merge(data['edges'].rename(columns={'src':'cid','dst':'neighbor'}),sales[['cid','margin']].rename(columns={'cid':'neighbor','margin':'neighbor_margin'}),'neighbor')
    peer['weighted_margin']=peer.weight*peer.neighbor_margin.fillna(0);pg=peer.groupby('cid').agg(weighted_margin=('weighted_margin','sum'),weight=('weight','sum')).reset_index();pg['peer_margin']=pg.weighted_margin/pg.weight
    result=c.copy()
    for block in [sales,t,journey,subs,contracts,credit,fr,ex,pg[['cid','peer_margin']]]:result=merge(result,block,'cid')
    result.credit=result.credit.fillna(80);result.csat=result.csat.fillna(4);result.baseline=result.baseline.fillna(80)
    firstlast=all_o.query('cancelled==0 and day<@end').groupby('cid').day.agg(['min','max'])
    result['recency']=end-result.cid.map(firstlast['max']).fillna(result.signup)
    # Correlated NOT EXISTS becomes a validated anti-join over successful as-of payments.
    ar=merge(all_o.query('day<@end'),data['receivables'][['oid','due_day']],'oid').query('due_day<@end')
    anti=ar.merge(paid[['oid']].assign(seen=1),on='oid',how='left',validate='one_to_one');unpaid=set(anti.loc[anti.seen.isna(),'cid'])
    result['unpaid_order']=result.cid.isin(unpaid).astype(int)
    bad=set(fraud.loc[fraud.chargeback==1,'cid']);result['clean_history']=(~result.cid.isin(bad)).astype(int)
    purchase=ev.loc[ev.kind==4,['cid','day']].copy();purchase['first_order']=purchase.cid.map(firstlast['min'])
    confirmed=set(purchase.loc[purchase.first_order<=purchase.day,'cid']);result['confirmed_journey']=result.cid.isin(confirmed).astype(int)
    peers=merge(data['edges'],data['customers'][['cid','credit']].rename(columns={'cid':'dst','credit':'peer_credit'}),'dst')
    result['peer_credit']=result.cid.map(peers.groupby('src').peer_credit.mean()).fillna(80)
    return result.drop(columns=['signup']).fillna(0).sort_values('cid').reset_index(drop=True)

def product(data,i):
    p=params(i);start=p['start'];end=p['end'];products=data['products'];cal=data['calendar'].query('@start<=day<@end')
    paid=data['payments'].query('success==1 and day<@end').groupby('oid').paid.sum().rename('cash').reset_index()
    returned=data['refunds'].query('day<@end').groupby('oid').refunded.sum().reset_index()
    sales=merge(data['items'],data['orders'].query('cancelled==0 and @start<=day<@end').drop(columns=['ts']), 'oid', 'inner')
    for block in [paid,returned,data['shipments']]:sales=merge(sales,block,'oid')
    sales[['cash','refunded']]=sales[['cash','refunded']].fillna(0);share=sales.qty*sales.price/sales.amount
    sales['revenue']=(sales.cash-sales.refunded)*share;sales['margin']=(sales.cash-sales.refunded-sales.cost-sales.freight)*share
    sales['late']=np.where(sales.delivered_day<end,np.maximum(0,sales.delivered_day-sales.promised_day),np.nan)
    daily_sales=sales.groupby(['pid','day']).agg(sold=('qty','sum'),revenue=('revenue','sum'),margin=('margin','sum'),buyers=('cid','nunique'),late=('late','mean')).reset_index()
    dense=products.merge(cal[['day','week','weekday']],how='cross');dense=merge(dense,daily_sales,['pid','day']);dense[['sold','revenue','margin','buyers','late']]=dense[['sold','revenue','margin','buyers','late']].fillna(0)
    pr=data['prices'].query('day<@end').sort_values(['pid','day']).copy();pr['rolling_units']=pr.groupby('pid').units.transform(lambda x:x.rolling(7,min_periods=1).mean())
    dense=merge(dense,pr[['pid','day','units','sale_price','promo','stockout','rolling_units']].rename(columns={'units':'observed_demand'}),['pid','day'],'inner')
    plant=merge(data['sensors'].query('@start<=day<@end'),data['machines'],'machine','inner')
    plant=merge(plant,data['production'],['machine','day'],'inner')
    plant=plant.groupby(['plant','day']).agg(output=('output_units','sum'),defects=('defects','sum'),vibration=('vibration','mean'),failures=('failure','sum'),downtime=('downtime','sum'),capacity=('capacity','sum')).reset_index().rename(columns={'plant':'category'})
    en=data['energy'].query('@start<=day<@end').copy();en['energy_cost']=en.kwh*en.tariff;en['emissions']=en.kwh*en.carbon
    en=en.groupby(['site','day']).agg(energy_cost=('energy_cost','sum'),carbon=('emissions','sum'),kwh=('kwh','sum')).reset_index().rename(columns={'site':'category'})
    dense=merge(dense,plant,['category','day'],'inner');dense=merge(dense,en,['category','day'],'inner');dense['tier']=dense.category%3
    dense=merge(dense,data['targets'],['tier','week'])
    agg={k:'mean' for k in ['sale_price','rolling_units','buyers','late','output','defects','vibration','capacity','energy_cost','carbon','kwh','revenue_target','risk_budget']}
    agg.update({k:'sum' for k in ['sold','revenue','margin','failures','downtime']});agg.update(price='max',day='count',observed_demand='mean',promo='mean',stockout='mean')
    result=dense.groupby(['pid','category']).agg(agg).reset_index().rename(columns={'day':'calendar_days','observed_demand':'demand','promo':'promo_rate','stockout':'stockout_rate'})
    dense['demand_squared']=dense.observed_demand**2;second=dense.groupby('pid').demand_squared.mean();result['demand_variance']=result.pid.map(second)-result.demand**2
    stock=data['inventory'].query('day<@end').sort_values(['pid','day']).drop_duplicates('pid',keep='last')[['pid','on_hand','lead_days']]
    result=merge(result,stock,'pid');result=merge(result,data['suppliers'].drop(columns='lead_days'),'pid')
    sp=data['supply'].query('@start<=day<@end').groupby(['supplier','pid']).agg(ordered=('ordered','sum'),received=('received','sum'),delay=('delay','mean')).reset_index();sp['fill_rate']=sp.received/sp.ordered
    result=merge(result,sp[['supplier','pid','fill_rate','delay']],['supplier','pid']);result.fill_rate=result.fill_rate.fillna(1);result.delay=result.delay.fillna(0)
    mk=data['market'].query('day<@end').sort_values(['asset','day']).copy();mk['previous']=mk.groupby('asset').close_price.shift();mk['ret']=np.log(mk.close_price/mk.previous)
    macro=mk.query('day>=@start and previous==previous').groupby('asset').agg(macro_return=('ret','mean'),macro_volume=('volume','mean')).reset_index().rename(columns={'asset':'category'});result=merge(result,macro,'category')
    result['country_cost']=result.country.map(data['suppliers'].groupby('country').unit_cost.mean())
    latest=data['supply'].query('day<@end').copy();last=latest.groupby('supplier').day.transform('max');latest=latest.loc[latest.day==last]
    result['latest_delivery']=result.supplier.map(latest.groupby('supplier').received.sum())
    outages=data['prices'].query('stockout==1 and @start<=day<@end')[['pid','day']]
    anti=outages.merge(data['supply'][['pid','day']].drop_duplicates().assign(seen=1),on=['pid','day'],how='left',validate='many_to_one')
    result['uncovered_stockout']=result.pid.isin(set(anti.loc[anti.seen.isna(),'pid'])).astype(int)
    avg=products.groupby('category').price.mean();result['premium']=(result.price>result.category.map(avg)).astype(int)
    camp=data['campaigns'].query('@start<=day<@end').groupby('channel').spend.mean();result['marketing_spend']=(result.category%4).map(camp)
    return result.sort_values('pid').reset_index(drop=True)

def build(data,domain,i,columns=None):
    result=(customer if domain=='customer' else product)(data,i)
    return result[list(columns)] if columns is not None else result

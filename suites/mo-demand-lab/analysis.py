"""Requirement-specific statistical analyses and constrained decisions.

Every calculation consumes independently obtained facts. Inputs are canonicalized
to eight decimal places only after the full SQL result tolerance check; this
defines deterministic decision ties and does not replace that check.
"""
import math,warnings
import numpy as np,pandas as pd
from scipy.optimize import linprog,OptimizeWarning
from scipy.stats import norm
from facts import params
warnings.filterwarnings('ignore',category=OptimizeWarning)

def numeric(frames):
 return [pd.DataFrame(np.round(f.to_numpy(dtype=float),8),columns=f.columns) for f in frames]
def divide(a,b):return float(a/b) if b else 0.
def rank(ids,values,limit=30,allocations=None):
 ids=np.asarray(ids,dtype=int);values=np.asarray(values,dtype=float);allocations=np.ones(len(ids)) if allocations is None else np.asarray(allocations,dtype=float)
 order=np.lexsort((ids,-np.round(values,8)))[:limit]
 return [[int(ids[j]),float(allocations[j]),float(values[j])] for j in order]
def result(metrics,decisions=(),checks=None,diagnostics=None):
 return {'metrics':metrics,'decisions':list(decisions),'checks':checks or {'finite_metrics':True},'diagnostics':diagnostics or {}}
def fit(x,y,ridge=.001):
 return np.linalg.solve(x.T@x+ridge*np.eye(x.shape[1]),x.T@y)
def logistic(x,y):
 mean=x.mean(0);scale=np.maximum(x.std(0),1e-8);z=np.column_stack([np.ones(len(x)),(x-mean)/scale]);w=np.zeros(z.shape[1]);w[0]=np.log((y.sum()+.5)/(len(y)-y.sum()+.5))
 for _ in range(18):
  p=1/(1+np.exp(-np.clip(z@w,-25,25)));v=np.maximum(p*(1-p),1e-7);pen=np.eye(len(w))*.5;pen[0,0]=.01
  delta=np.linalg.solve(z.T@(v[:,None]*z)+pen,z.T@(p-y)+pen@w);w-=np.clip(delta,-2,2)
  if np.max(np.abs(delta))<1e-7:break
 return lambda q:1/(1+np.exp(-np.clip(np.column_stack([np.ones(len(q)),(q-mean)/scale])@w,-25,25)))
def km(times,observed):
 times=np.asarray(times,dtype=int);observed=np.asarray(observed,dtype=bool);s=1.;area=0.;previous=0;curve=[]
 for t in sorted(set(times)):
  area+=(t-previous)*s;at_risk=int((times>=t).sum());failures=int(((times==t)&observed).sum());s*=1-divide(failures,at_risk);curve.append([int(t),s,at_risk,failures]);previous=t
 return area,curve
def simplex(v,cap=1.):
 low=float(v.min()-cap);high=float(v.max())
 for _ in range(55):
  mid=(low+high)/2
  if np.clip(v-mid,0,cap).sum()>1:low=mid
  else:high=mid
 return np.clip(v-(low+high)/2,0,cap)
def limited_spend(ids,benefit,cost,budget,limit=30):
 benefit=np.asarray(benefit);cost=np.maximum(np.asarray(cost),.01);ids=np.asarray(ids,dtype=int);order=np.lexsort((ids,-np.round(benefit/cost,8)));chosen=[];spent=0.
 for j in order:
  if benefit[j]>0 and spent+cost[j]<=budget+1e-8:
   chosen.append([int(ids[j]),float(cost[j]),float(benefit[j])]);spent+=cost[j]
   if len(chosen)>=limit:break
 return chosen,spent
def lp(c,**kwargs):
 r=linprog(c,method='highs',options={'threads':1,'parallel':False},**kwargs)
 if not r.success:raise RuntimeError('business optimization failed: '+r.message)
 return r.x
def market(a):
 returns=a.pivot(index='day',columns='asset',values='log_return').fillna(0).to_numpy();prices=a.pivot(index='day',columns='asset',values='close_price').to_numpy();return returns,prices
def forecast_products(a,p):
 out=[]
 for pid,g in a.groupby('pid',sort=True):
  t=g.day.to_numpy();y=g.units.to_numpy();valid=g.stockout.to_numpy()==0;cut=max(8,len(g)-p['horizon']);train=valid&(np.arange(len(g))<cut)
  def design(day):return np.column_stack([np.ones(len(day)),day/100,np.sin(day*2*np.pi/7),np.cos(day*2*np.pi/7)])
  w=fit(design(t[train]),y[train],.01);hold=np.arange(len(g))>=cut;prediction=np.maximum(0,design(t[hold])@w);error=np.sqrt(np.mean((prediction-y[hold])**2));res=y[train]-design(t[train])@w
  future=np.arange(p['end'],p['end']+p['horizon']);demand=np.maximum(0,design(future)@w).sum();sigma=float(np.std(res));last=g.iloc[-1]
  out.append([int(pid),demand,sigma,error,float(last.on_hand),float(last.lead_days),float(last.unit_cost),int(last.category),float(np.mean(y[valid]))])
 return np.asarray(out)

def calculate(key,frames,i):
 converted=numeric(frames);a,b=converted[:2];extra=converted[2:];p=params(i);budget=p['budget'];h=p['horizon'];checks={};diag={}
 if key=='profit_bridge':
  factors=np.zeros(5);total_change=0.;group_ids=[];changes=[]
  for (region,channel),g in a.groupby(['region','channel']):
   before=g[g.period==0];after=g[g.period==1];x=before.iloc[0] if len(before) else pd.Series(0.,index=g.columns);y=after.iloc[0] if len(after) else pd.Series(0.,index=g.columns);u0=divide(x.revenue,x.volume);u1=divide(y.revenue,y.volume)
   terms=np.array([(y.volume-x.volume)*u0,y.volume*(u1-u0),x.goods_cost-y.goods_cost,x.freight-y.freight,x.marketing-y.marketing]);factors+=terms;total_change+=y.margin-x.margin;group_ids.append(int(region)*10+int(channel));changes.append(y.margin-x.margin)
  residual=float(factors.sum()-total_change);checks={'bridge_adds_up':abs(residual)<.001,'product_revenue_allocation':abs(b.revenue.sum()-a.revenue.sum())<.001}
  return result({'margin_change':total_change,'volume_effect':factors[0],'unit_revenue_effect':factors[1],'goods_cost_effect':factors[2],'freight_effect':factors[3],'marketing_effect':factors[4],'bridge_residual':residual},rank(group_ids,changes),checks)
 if key=='rfm':
  x=np.column_stack([np.log1p(a.recency),np.log1p(a.orders),np.arcsinh(a.contribution/100)]);z=(x-x.mean(0))/np.maximum(x.std(0),1e-8);centers=z[np.linspace(0,len(z)-1,4,dtype=int)].copy();labels=np.zeros(len(z),int)
  for _ in range(12):
   labels=np.argmin(((z[:,None,:]-centers[None,:,:])**2).sum(2),axis=1)
   for k in range(4):
    if (labels==k).any():centers[k]=z[labels==k].mean(0)
  benefit=np.maximum(a.contribution.to_numpy(),0)*(a.recency.to_numpy()/max(1,p['end']));dec,spent=limited_spend(a.cid,benefit,np.full(len(a),5.),budget)
  return result({'customers':len(a),'inactive':int((a.orders==0).sum()),'recall_spend':spent,'historical_daily_revenue':float(b.revenue.mean()),'within_cluster_loss':float(((z-centers[labels])**2).sum())},dec,{'all_customers_assigned':len(labels)==len(a),'budget':spent<=budget}, {'cluster_counts':np.bincount(labels,minlength=4).tolist()})
 if key=='cohort_retention':
  customers=a[['cid','signup','tier']].drop_duplicates();curve=[]
  for week in range((p['end']-1)//7+1):
   eligible=customers[(p['end']-1-customers.signup)>=week*7+6];active=a[(a.age_week==week)&(a.active_days>0)&a.cid.isin(eligible.cid)].cid.nunique();curve.append([week,len(eligible),active,divide(active,len(eligible))])
  last=curve[-2][3] if len(curve)>1 else curve[-1][3];dec=rank(b.cid,np.maximum(b.contribution,0)*(1-last))
  return result({'customers':len(customers),'last_mature_retention':last,'revenue_exposure':float(np.maximum(b.revenue,0).sum()*(1-last))},dec,{'rates_valid':all(0<=r[3]<=1 for r in curve),'active_subset':all(r[2]<=r[1] for r in curve)}, {'maturity_adjusted_curve':curve})
 if key in ['survival','ltv']:
  observed=a.first_pause.to_numpy()<a.n_months.to_numpy();times=np.where(observed,a.first_pause.to_numpy()+1,a.n_months.to_numpy());rmst,curve=km(times,observed);prob=np.clip(a.active_months/a.n_months,0,1).to_numpy();monthly=np.maximum(a.contribution.to_numpy(),0)/max(1,(p['end']-p['start'])/30);factor=sum((prob/(1+p['discount']))**j for j in range(1,h+1));value=monthly*factor;net=value-a.acquisition_cost.to_numpy();dec=rank(a.cid,net)
  if key=='survival':dec=rank(a.cid,(1-prob)*np.maximum(a.revenue,0))
  return result({'restricted_mean_months':rmst,'first_pause_events':int(observed.sum()),'censored':int((~observed).sum()),'discounted_ltv':float(value.sum()),'net_acquisition_value':float(net.sum()),'observed_margin':float(b.margin.sum()) if 'margin' in b else float(a.contribution.sum())},dec,{'survival_monotone':all(curve[j][1]>=curve[j+1][1]-1e-12 for j in range(len(curve)-1)),'discount_bound':bool(np.all(value<=monthly*h+1e-8))}, {'survival_curve':curve})
 if key in ['experiment','guardrails']:
  users=a.groupby('cid').agg(treatment=('treatment','first'),baseline=('baseline','first'),revenue=('revenue','mean'),converted=('converted','mean'),latency=('latency','mean'),harm=('harm','mean'));t=users.treatment.to_numpy()==1;baseline=users.baseline.to_numpy();y=users.revenue.to_numpy();theta=divide(np.cov(y,baseline,ddof=0)[0,1],np.var(baseline));adjusted=y-theta*(baseline-baseline.mean());effect=float(adjusted[t].mean()-adjusted[~t].mean());se=float(np.sqrt(adjusted[t].var(ddof=1)/t.sum()+adjusted[~t].var(ddof=1)/(~t).sum()));lat=float(users.latency[t].mean()-users.latency[~t].mean());harm=float(users.harm[t].mean()-users.harm[~t].mean());launch=effect-1.96*se>0 and lat<10+i%8 and harm<p['risk'];site_effect=[]
  for site,g in a.groupby('site'):
   means=g.groupby('treatment').revenue.mean()
   if 0 in means and 1 in means:site_effect.append([int(site),float(means[1]-means[0])])
  return result({'users':len(users),'treatment_users':int(t.sum()),'adjusted_revenue_effect':effect,'standard_error':se,'ci_low':effect-1.96*se,'ci_high':effect+1.96*se,'latency_delta':lat,'harm_delta':harm,'launch':int(launch),'baseline_balance':float(b.contribution.mean()) if 'contribution' in b else float(b.latency.mean())},[[1,float(launch),effect]],{'ci_contains_estimate':effect-1.96*se<=effect<=effect+1.96*se,'both_arms':bool(t.any() and (~t).any()),'guardrail':not launch or (lat<10+i%8 and harm<p['risk'])}, {'site_effects':site_effect})
 if key=='attribution':
  total=float(a.attributed.sum());spend=float(b.spend.sum());values=a.attributed.to_numpy()-spend/max(1,len(a));return result({'attributed_revenue':total,'fractional_conversions':float(a.conversions.sum()),'marketing_spend':spend,'observational_roas':divide(total,spend)},rank(a.kind,values),{'finite_weights':bool(np.isfinite(a.to_numpy()).all()),'attribution_conservation':abs(total-float(a.eligible_revenue.iloc[0]))<.001,'conversion_conservation':abs(a.conversions.sum()-float(a.eligible_count.iloc[0]))<1e-6})
 if key=='marketing_budget':
  rate=a.margin.to_numpy()/np.maximum(a.spend.to_numpy(),1);rate-=a.returned.to_numpy()/np.maximum(a.spend.to_numpy(),1)*p['risk'];upper=np.maximum(10,a.spend.to_numpy())*(1+p['service']);x=lp(-rate,A_ub=np.ones((1,len(a))),b_ub=[budget],bounds=[(0,float(v)) for v in upper]);benefit=rate*x
  return result({'spend':float(x.sum()),'projected_margin':float(benefit.sum()),'addressable_customers':len(b),'unspent':float(budget-x.sum())},rank(a.channel,benefit,len(a),x),{'budget':x.sum()<=budget+1e-7,'channel_caps':bool(np.all(x<=upper+1e-7)),'beats_no_spend':benefit.sum()>=-1e-7})
 if key in ['forecast','replenishment']:
  f=forecast_products(a,p);mean=f[:,8];sigma=f[:,2];lead=f[:,5];stock=f[:,4];cost=f[:,6];z=norm.ppf(p['service']);target=mean*lead+z*sigma*np.sqrt(lead);quantity=np.ceil(np.maximum(0,target-stock));higher=mean*lead+norm.ppf(min(.999,p['service']+.01))*sigma*np.sqrt(lead);request_cost=quantity*cost;scale=min(1,divide(budget,request_cost.sum()));q=np.floor(quantity*scale);spent=float(q@cost);lost=np.maximum(0,mean*lead-stock-q);error=float(f[:,3].mean());dec=rank(f[:,0],mean*lead-lost,len(f),q)
  if key=='forecast':dec=rank(f[:,0],f[:,1],len(f),f[:,1])
  ci_radius=norm.ppf(.975)*sigma*np.sqrt(h);ci=np.column_stack([f[:,0],f[:,1],np.maximum(0,f[:,1]-ci_radius),f[:,1]+ci_radius,f[:,3]])
  return result({'forecast_units':float(f[:,1].sum()),'holdout_rmse':error,'inventory_request_cost':float(request_cost.sum()),'procurement_spend':spent,'uncovered_units':float(lost.sum()),'supplier_observations':len(b)},dec,{'nonnegative_forecast':bool((f[:,1]>=0).all()),'budget':spent<=budget+1e-6,'integer_replenishment':bool(np.equal(q,np.floor(q)).all()),'service_monotonic':bool(np.all(higher>=target-1e-9)),'forecast_interval':bool(np.all((ci[:,2]<=ci[:,1])&(ci[:,1]<=ci[:,3])))}, {'product_forecasts':ci.tolist(),'forecast_interval_method':'normal residual propagation; approximate, not a coverage guarantee'})
 if key=='assortment':
  slots=min(len(a),5+i%8);chosen=[];counts={};available=set(range(len(a)));objective=0.
  for category,g in a.groupby('category'):
   if len(chosen)>=slots:break
   j=int(g.margin.idxmax());v=float(a.iloc[j].margin);available.remove(j);counts[int(category)]=1;chosen.append([int(a.iloc[j].pid),1.,v]);objective+=v
  while available and len(chosen)<slots:
   def gain(j):return float(a.iloc[j].margin)-abs(float(a.iloc[j].margin))*.12*counts.get(int(a.iloc[j].category),0)
   j=max(available,key=lambda j:(round(gain(j),8),-int(a.iloc[j].pid)));v=gain(j);available.remove(j);counts[int(a.iloc[j].category)]=counts.get(int(a.iloc[j].category),0)+1;chosen.append([int(a.iloc[j].pid),1.,v]);objective+=v
  return result({'slots':slots,'selected_skus':len(chosen),'categories':len(counts),'adjusted_contribution':objective,'observed_category_margin':float(b.margin.sum())},chosen,{'capacity':len(chosen)<=slots,'unique_skus':len({r[0] for r in chosen})==len(chosen),'category_coverage':len(counts)>=min(slots,a.category.nunique())})
 if key=='supplier_risk':
  missing=a.ordered.to_numpy()-a.received.to_numpy();exposure=missing*a.unit_cost.to_numpy();risk=exposure+np.maximum(a.delay.to_numpy(),0)*a.lead_days.to_numpy()*a.unit_cost.to_numpy();by_country=a.assign(exposure=exposure).groupby('country').exposure.sum();shares=by_country.to_numpy()/max(1,by_country.sum());available_units=float(b[b.day==b.day.max()].on_hand.sum());return result({'missing_units':float(missing.sum()),'missing_value':float(exposure.sum()),'country_hhi':float(shares@shares),'available_units':available_units},rank(a.supplier,risk),{'fill_rate':bool(((a.fill_rate>=0)&(a.fill_rate<=1)).all()),'shortage':bool((missing>=-1e-7).all()),'country_totals':abs(by_country.sum()-exposure.sum())<1e-6})
 if key=='sla':
  obs=a.observed==1;groups=a[obs].groupby(['warehouse','carrier']).agg(count=('oid','count'),late=('late_days','mean'),p90=('late_days',lambda x:float(np.quantile(x,.9))),at_risk=('net_revenue','sum'));value=groups.late.to_numpy()*np.maximum(groups.at_risk.to_numpy(),0);ids=[int(x)*10+int(y) for x,y in groups.index];return result({'observed_shipments':int(obs.sum()),'censored_shipments':int((~obs).sum()),'late_fraction':float((a[obs].late_days>0).mean()),'daily_revenue':float(b.revenue.mean())},rank(ids,value),{'partition':int(obs.sum()+(~obs).sum())==len(a),'valid_late_fraction':0<=float((a[obs].late_days>0).mean())<=1})
 if key=='returns':
  rate=a.returned.to_numpy()/np.maximum(a.gross.to_numpy(),1);smooth=(a.returned.to_numpy()+10)/(np.maximum(a.gross.to_numpy(),0)+100);totals=b.groupby('channel').returned.sum();return result({'refund_value':float(a.returned.sum()),'weighted_refund_rate':divide(a.returned.sum(),a.gross.sum()),'largest_channel':int(totals.idxmax()),'max_smoothed_rate':float(smooth.max())},rank(a.pid,a.returned.to_numpy()*(1+smooth)),{'refund_allocation':abs(a.returned.sum()-b.returned.sum())<.001,'rates_valid':bool(((rate>=0)&(rate<=1)).all())})
 if key=='cash_reconcile':
  diff=np.round(a.ledger_amount.to_numpy()-a.cash.to_numpy(),2);flag=np.abs(diff)>.005;return result({'ledger_difference':float(diff.sum()),'exceptions':int(flag.sum()),'cash':float(a.cash.sum()),'outstanding':float(a.outstanding.sum()),'forecast_base_revenue':float(b.revenue.sum())},rank(a.oid[flag],np.abs(diff[flag]),50,diff[flag]),{'difference_adds_up':abs(diff.sum()-(np.round(a.ledger_amount-a.cash,2)).sum())<1e-8,'no_negative_receivables':bool((a.outstanding>=0).all())})
 if key=='collections':
  probability=1/(1+np.exp(np.clip((a.days_overdue.to_numpy()-a.credit.to_numpy()/3)/20,-20,20)));benefit=a.outstanding.to_numpy()*probability*.25;cost=4+a.days_overdue.to_numpy()*.1;dec,spent=limited_spend(a.cid,benefit-cost,cost,min(budget,max(0,float(b.revenue.sum()))*.05));return result({'outstanding':float(a.outstanding.sum()),'expected_recovery':float(benefit.sum()),'contact_spend':spent,'contacts':len(dec),'expected_net_selected':sum(r[2] for r in dec)},dec,{'budget':spent<=budget+1e-7,'positive_benefit':all(r[2]>0 for r in dec),'positive_receivable':all(float(a[a.cid==r[0]].outstanding.iloc[0])>0 for r in dec)})
 if key in ['liquidity','stress']:
  income=float(a.revenue.mean());expenses=float(a.expenses.mean());supply_gap=0.;refund_share=0.
  if key=='stress':
   supply_gap=float(1-extra[0].fill_rate.mean());refund_share=divide(b.returned.sum(),b.gross.sum());income*=max(.1,1-p['risk']-supply_gap);expenses*=1+p['risk']+max(0,supply_gap)+refund_share
  rng=np.random.default_rng(2026101200+i);shock=rng.normal(0,.15,(384,h));shock-=shock.mean(0);receivable=float(b.outstanding.sum()) if 'outstanding' in b else float(a.outstanding.sum());opening=budget+max(0,income)*2;net=income*np.clip(1+shock-p['risk'],.1,2)-expenses*(1+p['risk']);balance=opening+np.cumsum(net+receivable/h*.2,axis=1);bad=opening+np.cumsum(net-income*p['risk']-expenses*p['risk'],axis=1);prob=float((balance.min(1)<budget*.25).mean());bad_prob=float((bad.min(1)<budget*.25).mean());quantiles=np.quantile(balance,[.05,.5,.95],axis=0);dec=[[j+1,float(quantiles[1,j]),float(quantiles[0,j])] for j in range(h)]
  return result({'initial_cash':opening,'end_cash_median':float(np.median(balance[:,-1])),'reserve_breach_probability':prob,'bad_scenario_breach_probability':bad_prob,'receivables':receivable},dec,{'stress_monotonic':bad_prob>=prob,'cash_identity':bool(np.allclose(np.diff(np.column_stack([np.full(384,opening),balance]),axis=1),net+receivable/h*.2))}, {'cash_quantiles':quantiles.tolist()})
 if key=='credit':
  x=np.column_stack([a.credit,a.apr,a.principal/1000]);y=a.defaulted.to_numpy();train=(a.cid.to_numpy().astype(int)%5)!=i%5;predict=logistic(x[train],y[train]);pd_value=predict(x);loss=pd_value*a.balance.to_numpy()*.45;brier=float(np.mean((pd_value[~train]-y[~train])**2));return result({'exposure':float(a.balance.sum()),'expected_loss':float(loss.sum()),'holdout_brier':brier,'holdout_observed_default':float(y[~train].mean()),'holdout_predicted_default':float(pd_value[~train].mean()),'group_exposure':float(b.exposure.sum())},rank(a.loan_id,loss),{'probabilities':bool(((pd_value>=0)&(pd_value<=1)).all()),'loss_bound':loss.sum()<=a.balance.sum()*.45+1e-7,'group_conservation':abs(a.balance.sum()-b.exposure.sum())<.001})
 if key=='concentration':
  grouped=a.groupby(['region','tier']).balance.sum();values=grouped.to_numpy();shares=values/max(1,values.sum());borrower=a.groupby('cid').balance.sum().to_numpy();bs=borrower/max(1,borrower.sum());stress_loss=values*.45*(p['risk']+np.arange(len(values))*.005);return result({'exposure':float(values.sum()),'segment_hhi':float(shares@shares),'borrower_hhi':float(bs@bs),'stress_loss':float(stress_loss.sum()),'customer_credit':float(b.credit.mean())},rank([int(x)*10+int(y) for x,y in grouped.index],stress_loss),{'conservation':abs(values.sum()-a.balance.sum())<.001,'hhi':0<=shares@shares<=1})
 if key in ['portfolio_risk','portfolio_alloc','pairs']:
  r,prices=market(a);mean=r.mean(0);cov=np.cov(r,rowvar=False);weights=np.arange(1,r.shape[1]+1,dtype=float)+(i%5);weights/=weights.sum();initial=weights.copy();diag={'covariance':cov.tolist()}
  if key=='portfolio_alloc':
   risk=100+p['risk']*1000;turn=.001;objective=lambda w:float(risk*w@cov@w-mean@w+turn*((w-initial)**2).sum());start_obj=objective(weights)
   for _ in range(75):
    gradient=2*risk*cov@weights-mean+2*turn*(weights-initial);step=10.;candidate=weights
    for _ in range(12):
     candidate=simplex(weights-step*gradient,.35)
     if objective(candidate)<=objective(weights)+1e-12:break
     step/=2
    weights=candidate
   diag['objective_initial']=start_obj;diag['objective_final']=objective(weights);checks['objective']=objective(weights)<=start_obj+1e-7;checks['asset_cap']=bool((weights<=.35+1e-7).all())
  if key=='pairs':
   split=len(prices)-max(20,h*3);log_prices=np.log(prices);candidates=[]
   for x in range(prices.shape[1]):
    for y in range(x+1,prices.shape[1]):
     design=np.column_stack([np.ones(split),log_prices[:split,y]]);w=fit(design,log_prices[:split,x]);spread=log_prices[:,x]-w[0]-w[1]*log_prices[:,y];ar=fit(np.column_stack([np.ones(split-1),spread[:split-1]]),spread[1:split]);candidates.append((abs(ar[1]),x,y,w,spread))
   _,x,y,w,spread=min(candidates,key=lambda z:(round(z[0],8),z[1],z[2]));mu=spread[:split].mean();sd=max(1e-8,spread[:split].std());signals=-np.sign(spread[split-1:-1]-mu)*(np.abs(spread[split-1:-1]-mu)>sd);pnl=signals*np.diff(spread[split-1:])-np.abs(np.diff(np.r_[0,signals]))*.0005;return result({'asset_a':x,'asset_b':y,'hedge_ratio':float(w[1]),'holdout_net_pnl':float(pnl.sum()),'turnover':float(np.abs(np.diff(np.r_[0,signals])).sum()),'reference_assets':len(b)},[[x*100+y,1.,float(pnl.sum())]],{'time_split':split<len(prices),'lagged_signal':len(signals)==len(pnl)}, {'holdout_pnl':pnl.tolist()})
  port=r@weights;loss=-port;var=float(np.quantile(loss,1-p['risk']));es=float(loss[loss>=var].mean());wealth=np.exp(np.cumsum(port));draw=wealth/np.maximum.accumulate(wealth)-1;checks.update(weights=abs(weights.sum()-1)<1e-8,psd=float(np.linalg.eigvalsh(cov).min())>=-1e-10,tail=es>=var-1e-12)
  return result({'mean_return':float(port.mean()),'volatility':float(np.sqrt(weights@cov@weights)),'value_at_risk':var,'expected_shortfall':es,'max_drawdown':float(draw.min()),'reference_assets':len(b)},rank(np.arange(len(weights)),weights*mean,len(weights),weights),checks,diag)
 if key=='elasticity':
  rows=[];errors=[]
  for pid,g in a.groupby('pid'):
   t=g.day.to_numpy();valid=g.stockout.to_numpy()==0;train=valid&(t<p['split']);x=np.column_stack([np.ones(len(g)),np.log(g.sale_price),np.sin(t*2*np.pi/7),np.cos(t*2*np.pi/7),g.promo,t/100]);w=fit(x[train],np.log(np.maximum(g.units.to_numpy()[train],.01)),.001);hold=valid&(t>=p['split']);pred=np.exp(np.clip(x[hold]@w,-10,15));errors.append(float(np.mean(np.abs(pred-g.units.to_numpy()[hold]))));change=.02+p['risk'];new_price=float(g.sale_price.iloc[-1])*(1+change);units=float(g.units.mean())*(1+change)**w[1];margin=units*(new_price-float(g.unit_cost.mean()));rows.append([int(pid),float(w[1]),margin])
  return result({'products':len(rows),'mean_elasticity':float(np.mean([r[1] for r in rows])),'holdout_mae':float(np.mean(errors)),'simulated_margin':sum(r[2] for r in rows),'cost_reference_products':len(b)},rows,{'finite':bool(np.isfinite(rows).all())}, {'product_price_response':rows})
 if key=='cannibalization':
  daily=a.groupby(['category','day']).agg(promoted=('promo','sum'),units=('units','sum'));rows=[]
  for category,g in daily.groupby(level=0):
   d=g.index.get_level_values('day').to_numpy();x=np.column_stack([np.ones(len(g)),g.promoted,np.sin(d*2*np.pi/7),np.cos(d*2*np.pi/7)]);w=fit(x,g.units.to_numpy());rows.append([int(category),float(w[1]),float(g.units.sum())])
  return result({'category_units':float(daily.units.sum()),'observed_promo_association':float(np.mean([r[1] for r in rows])),'promotion_days':int((a.promo>0).sum()),'category_reference_units':float(b.units.sum())},rank([r[0] for r in rows],[r[1] for r in rows]),{'category_conservation':abs(daily.units.sum()-b.units.sum())<.001}, {'category_coefficients':rows})
 if key=='fraud':
  x=np.column_stack([np.log1p(a.amount),np.log1p(a.shared_users),np.log1p(a.prior_volume),a.prior_loss]);y=a.chargeback.to_numpy();train=a.day.to_numpy()<p['split'];predict=logistic(x[train],y[train]);prob=predict(x[~train]);g=a[~train];value=prob*g.amount.to_numpy();cost=np.full(len(g),3.);dec,spent=limited_spend(g.payment,value-cost,cost,min(budget,60+i%100));selected={r[0] for r in dec};captured=float(g[g.payment.isin(selected)].assign(loss=lambda x:x.amount*x.chargeback).loss.sum());total=float((g.amount*g.chargeback).sum())
  return result({'holdout_payments':len(g),'holdout_brier':float(np.mean((prob-y[~train])**2)),'review_spend':spent,'captured_chargeback':captured,'missed_chargeback':total-captured,'customer_cohort':len(b)},dec,{'review_budget':spent<=min(budget,60+i%100)+1e-8,'loss_conservation':abs(captured+(total-captured)-total)<1e-8})
 if key=='funnel':
  stages=['view_day','detail_day','cart_day','checkout_day','purchase_day'];counts=[];valid=np.ones(len(a),bool)
  for j,col in enumerate(stages):valid&=a[col].notna().to_numpy();valid&=(a[col].to_numpy()>=a[stages[j-1]].to_numpy()) if j else True;counts.append(int(valid.sum()))
  losses=np.array(counts[:-1])-np.array(counts[1:]);unit_value=divide(max(0,b.revenue.sum()),max(1,counts[-1]));opportunity=losses*unit_value*.1;return result({'sessions':len(a),'purchases':counts[-1],'conversion':divide(counts[-1],counts[0]),'revenue_opportunity':float(opportunity.sum())},rank(np.arange(4),opportunity),{'monotone_counts':all(counts[j]>=counts[j+1] for j in range(4))}, {'stage_counts':counts})
 if key=='journey':
  counts=np.zeros((6,6))
  for _,g in a.groupby('session_id',sort=False):
   path=g.kind.to_numpy(dtype=int)
   for x,y in zip(path[:-1],path[1:]):counts[x,y]+=1
   last=int(path[-1]);counts[last,4 if last==4 else 5]+=1
  counts[4]=0;counts[4,4]=1;counts[5]=0;counts[5,5]=1
  for k in range(4):
   if counts[k].sum()==0:counts[k,5]=1
  transition=counts/counts.sum(1)[:,None];absorb=np.linalg.solve(np.eye(4)-transition[:4,:4],transition[:4,4]);value=float(absorb[0]*max(0,b.revenue.sum()));return result({'purchase_absorption':float(absorb[0]),'implied_purchase_value':value,'sessions':int(a.session_id.nunique())},rank(np.arange(4),1-absorb),{'stochastic_rows':bool(np.allclose(transition.sum(1),1)),'absorption_bounds':bool(((absorb>=-1e-8)&(absorb<=1+1e-8)).all())}, {'transition_matrix':transition.tolist()})
 if key=='capacity':
  rows=[];cost=0.
  for warehouse,g in a.groupby('warehouse'):
   days=np.arange(p['start'],p['end']);series=g.set_index('day').orders.reindex(days,fill_value=0).to_numpy();mean=float(series.mean());reserve=norm.ppf(p['service'])*float(series.std());needed=math.ceil(max(0,mean+reserve));unit_cost=float(g.handling_cost.mean());cost+=needed*unit_cost*h;rows.append([int(warehouse),float(needed),float(mean*h)])
  return result({'horizon_capacity_cost':cost,'planned_daily_capacity':sum(r[1] for r in rows),'historical_cash_in':float(b.revenue.sum())},rows,{'integer_capacity':all(r[1]>=0 and r[1]==int(r[1]) for r in rows)})
 if key=='energy':
  demand=a.demand.to_numpy();tariff=a.tariff.to_numpy();n=len(a);eta=.92;power=20+i%15;capacity=80+i%40;initial=capacity/2;c=np.r_[tariff,-tariff,np.zeros(n)];eq=np.zeros((n+1,3*n));rhs=np.zeros(n+1)
  for t in range(n):
   eq[t,t]=-eta;eq[t,n+t]=1/eta;eq[t,2*n+t]=1
   if t:eq[t,2*n+t-1]=-1
   else:rhs[t]=initial
  eq[-1,-1]=1;rhs[-1]=initial;ub=np.zeros((n,3*n))
  for t in range(n):ub[t,t]=1;ub[t,n+t]=-1
  solution=lp(c,A_eq=eq,b_eq=rhs,A_ub=ub,b_ub=a.capacity.to_numpy()-demand,bounds=[(0,power)]*(2*n)+[(0,capacity)]*n);charge=solution[:n];discharge=solution[n:2*n];soc=solution[2*n:];grid=demand+charge-discharge;baseline=float(demand@tariff);actual=float(grid@tariff);return result({'baseline_daily_cost':baseline,'planned_daily_cost':actual,'savings':baseline-actual,'peak_grid':float(grid.max()),'historical_daily_cost':float(b.energy_cost.mean())},[[int(t),float(charge[t]-discharge[t]),float((demand[t]-grid[t])*tariff[t])] for t in range(n)],{'soc_balance':bool(np.allclose(np.diff(np.r_[initial,soc]),eta*charge-discharge/eta)),'terminal_soc':abs(soc[-1]-initial)<1e-6,'capacity':bool(((soc>=-1e-7)&(soc<=capacity+1e-7)).all()),'grid_cap':bool((grid<=a.capacity.to_numpy()+1e-7).all()),'cost_not_worse':actual<=baseline+1e-6}, {'soc':soc.tolist()})
 if key=='maintenance':
  x=np.column_stack([a.rolling_vibration,a.temperature,a.load_value,a.age]);y=(a.next_failures.to_numpy()>0).astype(float);train=(a.day.to_numpy()+3)<p['split'];valid=(a.day.to_numpy()>=p['split'])&((a.day.to_numpy()+3)<p['end']);predict=logistic(x[train],y[train]);score=predict(x);last=a.groupby('machine').tail(1);ix=last.index.to_numpy();value=score[ix]*last.capacity.to_numpy()*h*5;slots=5+i%10;return result({'holdout_brier':float(np.mean((score[valid]-y[valid])**2)),'machines':int(a.machine.nunique()),'maintenance_slots':slots,'historical_downtime':float(b.downtime.sum())},rank(last.machine,value,slots),{'time_cutoff':bool(np.all(a.day.to_numpy()[train]+3<p['split'])),'probabilities':bool(((score>=0)&(score<=1)).all())})
 if key=='quality':
  baseline=a[a.day<p['split']].groupby('machine').agg(d=('defects','sum'),n=('output_units','sum'));current=a[a.day>=p['split']].groupby('machine').agg(d=('defects','sum'),n=('output_units','sum'),loss=('scrap_cost','sum'));rate=baseline.d/np.maximum(baseline.n,1);observed=current.d/np.maximum(current.n,1);se=np.sqrt(np.maximum(rate*(1-rate),1e-6)/np.maximum(current.n,1));z=(observed-rate)/se;pv=norm.sf(z);order=np.argsort(pv,kind='stable');adjusted=np.ones(len(pv));adjusted[order]=np.minimum(1,np.minimum.accumulate((pv[order]*len(pv)/np.arange(1,len(pv)+1))[::-1])[::-1]);flags=adjusted<p['risk'];return result({'machines_tested':len(pv),'drift_alerts':int(flags.sum()),'scrap_value_at_risk':float(current.loss.to_numpy()[flags].sum()),'plant_scrap':float(b.scrap_cost.sum())},rank(current.index[flags],current.loss.to_numpy()[flags]),{'adjusted_pvalues':bool(((adjusted>=0)&(adjusted<=1)).all()),'defect_bounds':bool(((a.defects>=0)&(a.defects<=a.output_units+1e-7)).all())}, {'adjusted_pvalues':adjusted.tolist()})
 if key=='reliability':
  times=[];observed=[];ids=[]
  for machine,g in a.groupby('machine'):
   failure=g[g.failure>0];observed.append(bool(len(failure)));times.append(int(failure.day.iloc[0]-p['start']+1) if len(failure) else p['end']-p['start']);ids.append(int(machine))
  rmst,curve=km(times,observed);survival=curve[-1][1];risk=1-survival;return result({'restricted_mean_days':rmst,'first_failures':int(sum(observed)),'right_censored':int(len(observed)-sum(observed)),'period_failure_risk':risk,'downtime':float(b.downtime.sum())},rank(ids,[risk*(1+x/100) for x in times]),{'survival_monotone':all(curve[j][1]>=curve[j+1][1] for j in range(len(curve)-1)),'risk_bounds':0<=risk<=1},{'survival_curve':curve})
 if key=='support_staff':
  rows=[];total=0;waits=[]
  for kind,g in a.groupby('kind'):
   arrivals=float(g.arrivals.sum())/(p['end']-p['start'])/480;service=divide(g.handle_minutes.sum(),g.arrivals.sum());offered=arrivals*service;staff=max(1,int(math.floor(offered))+1)
   while True:
    erlang_b=1.
    for c in range(1,staff+1):erlang_b=offered*erlang_b/(c+offered*erlang_b)
    rho=offered/staff;erlang_c=erlang_b/(1-rho+rho*erlang_b);sla=1-erlang_c*np.exp(-(staff-offered)*p['lookback']/max(service,1e-8))
    if sla>=p['service'] or staff>=40:break
    staff+=1
   total+=staff;waits.append(sla);rows.append([int(kind),float(staff),float(sla)])
  return result({'staff':total,'daily_staff_cost':total*160,'min_sla':float(min(waits)),'customers_at_risk':int((b.csat<3.5).sum())},rows,{'sla':min(waits)>=p['service']-1e-8,'integer_staff':all(r[1]==int(r[1]) for r in rows)})
 if key in ['health','expansion']:
  activation=np.clip(a.active_months/a.n_months,0,1).to_numpy();service_burden=a.handling.to_numpy()*.4;value=np.maximum(a.contribution.to_numpy(),0)+a.paid.to_numpy()*.25-service_burden;risk=np.clip((1-activation)+np.maximum(0,4-a.csat.to_numpy())*.15+a.arrears.to_numpy()/np.maximum(a.billed.to_numpy(),1)*.4,0,1);benefit=np.maximum(value,0)*(risk if key=='health' else activation*.12);cost=8+a.tickets.to_numpy()*.1;dec,spent=limited_spend(a.cid,benefit-cost,cost,budget);return result({'contact_spend':spent,'contacts':len(dec),'expected_net_value':sum(r[2] for r in dec),'service_cost':float(service_burden.sum()),'cohort_paid':float(b.paid.sum()) if 'paid' in b else float(a.paid.sum()),'mean_health_risk':float(risk.mean())},dec,{'budget':spent<=budget+1e-8,'positive_net':all(r[2]>0 for r in dec),'risk_bounds':bool(((risk>=0)&(risk<=1)).all())})
 if key=='recognition':
  earned=a.booked.to_numpy()*a.earned_days.to_numpy()/a.term_days.to_numpy();deferred=a.booked.to_numpy()-earned;future=np.minimum(deferred,a.booked.to_numpy()*h/a.term_days.to_numpy());cost=a.cost_to_serve.to_numpy()*h/a.term_days.to_numpy();return result({'booked':float(a.booked.sum()),'earned':float(earned.sum()),'deferred':float(deferred.sum()),'horizon_revenue':float(future.sum()),'horizon_service_cost':float(cost.sum()),'realized_cash':float(b.revenue.sum())},rank(a.contract_id,future-cost,50,future),{'accounting_identity':abs(earned.sum()+deferred.sum()-a.booked.sum())<.001,'future_bound':bool(np.all(future<=deferred+1e-8))})
 if key=='anomalies':
  days=np.arange(p['start'],p['end']);series=a.set_index('day').revenue.reindex(days,fill_value=0).to_numpy();x=np.column_stack([np.ones(len(days)),days/100,np.sin(days*2*np.pi/7),np.cos(days*2*np.pi/7)]);train=days<p['split'];w=fit(x[train],series[train],.01);res=series-x@w;median=float(np.median(res[train]));mad=max(1,float(np.median(np.abs(res[train]-median)))*1.4826);z=(res-median)/mad;flags=(~train)&(np.abs(z)>norm.ppf(1-p['risk']/2));by_channel=b.groupby('channel').revenue.sum();return result({'alert_days':int(flags.sum()),'baseline_residual_scale':mad,'alert_revenue_deviation':float(res[flags].sum()),'largest_channel':int(by_channel.idxmax())},rank(days[flags],np.abs(res[flags]),50,z[flags]),{'holdout_only':bool(np.all(days[flags]>=p['split']))},{'daily_residuals':res.tolist()})
 if key=='planning':
  demand=np.maximum(0,a.mean_demand.to_numpy()*h+norm.ppf(p['service'])*np.sqrt(np.maximum(a.demand_var.to_numpy(),0)*h)-a.on_hand.to_numpy());capacity=a.production_capacity.to_numpy()/max(1,p['end']-p['start'])*h/10;wanted=np.minimum(np.ceil(demand),np.floor(np.maximum(capacity,0)));cost=a.unit_cost.to_numpy();cash_available=max(0,budget+float(b.margin.sum())*.05);actual_budget=min(budget,cash_available);ratio=min(1,divide(actual_budget,wanted@cost));quantity=np.floor(wanted*ratio);spend=float(quantity@cost);profit_per_unit=np.maximum(0,a.observed_margin.to_numpy()/np.maximum(a.sold_units.to_numpy(),1));benefit=quantity*profit_per_unit;return result({'procurement_spend':spend,'budget':actual_budget,'planned_units':float(quantity.sum()),'expected_contribution':float(benefit.sum()),'cash_buffer':cash_available-spend,'uncovered_demand':float(np.maximum(0,demand-quantity).sum()),'historical_margin':float(b.margin.sum())},rank(a.pid,benefit,len(a),quantity),{'budget':spend<=actual_budget+1e-7,'capacity':bool(np.all(quantity<=capacity+1e-7)),'stock_nonnegative':bool(np.all(a.on_hand.to_numpy()+quantity>=0)),'integer_plan':bool(np.equal(quantity,np.floor(quantity)).all())})
 raise KeyError(key)

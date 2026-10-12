"""Independently coded pandas joins and NumPy window arithmetic, from original fixtures."""
import numpy as np,pandas as pd
from scenarios import params

def daily(data,i):
 p=params(i);s=data['entities'].query('@p["lo"]<=eid<@p["hi"]').copy();cal=data['calendar'].query('@p["start"]<=day<@p["d1"]');g=s.merge(cal,how='cross')
 m=data['measurements'];m=m[(m.eid.isin(s.eid))&(m.day>=p['start'])&(m.day<p['d1'])&(m.received_day<=p['snapshot'])].sort_values(['event_id','revision','rid']).drop_duplicates('event_id',keep='last');m=m[m.valid==1]
 md=m.groupby(['eid','day']).agg(sensor=('value','mean'),observations=('value','count'),raw_count=('value','size')).reset_index()
 original=data['measurements'];original=original[original.revision==0].groupby(['eid','day']).value.mean().rename('original_sensor').reset_index()
 rev=data['reversals'];rev=rev[rev.day<=p['snapshot']].groupby('tid').amount.sum().rename('reversed');t=data['trades'].merge(rev,left_on='tid',right_index=True,how='left');t['net']=np.where(t.settled==1,t.amount-t.reversed.fillna(0),0);td=t.groupby(['eid','day']).net.sum().reset_index()
 sh=data['shipments'];sh=sh[sh.day<=p['snapshot']].merge(data['orders'][['oid','day']],on='oid',suffixes=('','_order'));sh['late_qty']=np.where(sh.day-sh.day_order>3,sh.qty,0);sh=sh.groupby('oid').agg(shipped=('qty','sum'),late_qty=('late_qty','sum')).reset_index();o=data['orders'].merge(sh,on='oid',how='left');o[['shipped','late_qty']]=o[['shipped','late_qty']].fillna(0);od=o.groupby(['eid','day']).agg(demand=('qty','sum'),shipped=('shipped','sum'),late_qty=('late_qty','sum')).reset_index()
 ev=data['events'];ev=ev[ev.received_min<=28401120+p['snapshot']*1440].copy();ev['late_count']=(ev.received_min-ev.minute>1440).astype(int);ev['phase0']=(ev.kind==0).astype(int);ev['phase1']=(ev.kind==1).astype(int);ed=ev.groupby(['eid','day']).agg(event_count=('event_id','size'),late_count=('late_count','sum'),phase0=('phase0','sum'),phase1=('phase1','sum')).reset_index()
 q=g[['eid','day']].merge(data['outages'],on='eid',how='left');q=q[(q.start_day<=q.day)&(q.end_day>q.day)].groupby(['eid','day']).severity.sum().reset_index()
 pe=data['edges'].merge(md[['eid','day','sensor']],left_on='dst',right_on='eid');pe['weighted']=pe.weight*pe.sensor;pe['denominator']=np.where(pe.sensor.notna(),pe.weight,0);pe=pe.groupby(['src','day'])[['weighted','denominator']].sum().reset_index();pe['neighbor']=pe.weighted/pe.denominator.replace(0,np.nan);pe=pe.rename(columns={'src':'eid'})[['eid','day','neighbor']]
 a=g.merge(md,on=['eid','day'],how='left',validate='1:1').merge(original,on=['eid','day'],how='left',validate='1:1').merge(td,on=['eid','day'],how='left',validate='1:1').merge(od,on=['eid','day'],how='left',validate='1:1')
 a=a.merge(data['inventory'].rename(columns={'on_hand':'stock'}),on=['eid','day'],validate='1:1').merge(data['capacity'].rename(columns={'available':'capacity'}),on=['region','day'],validate='m:1').merge(data['weather'],on=['region','day'],validate='m:1').merge(data['prices'],on=['sector','day'],validate='m:1').merge(data['fx'],on=['region','day'],validate='m:1').merge(data['targets'],on=['sector','weekday'],validate='m:1').merge(q,on=['eid','day'],how='left',validate='1:1')
 pol=a.merge(data['policies'],on='eid');pol=pol[(pol.valid_from<=pol.day)&(pol.valid_to>pol.day)][['eid','day','budget']];a=a.merge(pol,on=['eid','day'],validate='1:1').merge(data['interventions'],on=['eid','day'],how='left',validate='1:1').merge(ed,on=['eid','day'],how='left',validate='1:1').merge(pe,on=['eid','day'],how='left',validate='1:1')
 for col in ['observations','raw_count','original_sensor','net','demand','shipped','late_qty','severity','effect','event_count','late_count','phase0','phase1','neighbor']:a[col]=a[col].fillna(0)
 a['y']=a.net*a.rate;a['x']=a.sensor.fillna(0)/a.scale+a.demand/a.target+a.temp/50+a.y/a.scale/20+a.severity-a.stock/100-a.capacity/200+a.effect+a.neighbor/a.scale/20+a.price/100+a.rate/10-a.budget/10000+a.late_qty/20+a.late_count/100
 return a.sort_values(['eid','day']).reset_index(drop=True)

def events(data,i):
 p=params(i);e=data['events'];s=data['entities'].query('@p["lo"]<=eid<@p["hi"]');e=e[(e.eid.isin(s.eid))&(e.day>=p['start'])&(e.day<p['d1'])&(e.received_min<=28401120+p['snapshot']*1440)].merge(s,on='eid').merge(data['calendar'][['day','weekday','offset_min']],on='day').sort_values(['eid','minute','event_id']).reset_index(drop=True);e['x']=e.magnitude.astype(float);e['civil_min']=e.minute+e.offset_min;e['rn']=e.groupby('eid').cumcount()+1;e['prev_min']=e.groupby('eid').minute.shift();e['prev_kind']=e.groupby('eid').kind.shift();return e

def roll(x,k,fn,exclude=False):
 x=np.asarray(x,float);out=[]
 for j in range(len(x)):
  a=x[max(0,j-k):j if exclude else j+1];good=a[~np.isnan(a)];out.append(fn(good) if len(good) else np.nan)
 return np.asarray(out)

def independently_check(data,f,i,reference):
 """Independent entire-output checks for 19 families, plus all 18-table base joins."""
 p=params(i);a=events(data,i) if f in [35,37,38,39,40,41,42] else daily(data,i);rows=[]
 if f>=46:
  score=a.x.to_numpy(float);depth=p['depth']+(4 if f==47 else -2 if f==48 else 0)
  for layer in range(depth):
   smooth=np.empty(len(a));span=np.empty(len(a));peer=np.empty(len(a));k=2+(layer+i)%9
   for ids in a.groupby('eid',sort=False).indices.values():
    v=score[ids];smooth[ids]=roll(v,k,np.mean);span[ids]=roll(v,k,np.max)-roll(v,k,np.min);peer[ids]=np.r_[v[0],v[:-1]]
   if f==47:peer=pd.Series(score).groupby([a.sector,a.day]).transform('mean').to_numpy()
   new=.53*score+.29*smooth+.18*peer+.013*span/(1+np.abs(span))
   if f==48:new+=.017*(score-peer)/(1+np.abs(score-peer))
   if f==49:new+=.009*(a.y.to_numpy()/a.budget.to_numpy())/(1+np.abs(a.y.to_numpy()/a.budget.to_numpy()))
   score=new
  a['score']=score;mask=a.day>=p['d0'];np.testing.assert_allclose(a.loc[mask,'score'],reference.score,rtol=1e-7,atol=1e-7);return {'native_deep_feedback':True}
 if f not in [0,1,2,3,4,5,6,11,13,18,21,33,35,37,38,39,41,43]:return {'native_base_only':True}
 for eid,g in a.groupby('eid',sort=False):
  g=g.reset_index(drop=True);x=g.x.to_numpy(float);k=p['k'];long=p['long'];h=p['h'];out={'eid':g.eid.to_numpy(),'day':g.day.to_numpy(),'x':x};lag=lambda v,n:np.r_[np.repeat(np.nan,n),np.asarray(v)[:-n]]
  if f==0:out.update(revenue=roll(g.y,k,np.sum),pressure=roll(x,long,np.mean),lag_revenue=lag(g.y,h))
  elif f==1:
   ship=roll(g.shipped,k,np.sum);dem=roll(g.demand,k,np.sum);dd=roll(g.demand,long,np.sum);out.update(shipped_sum=ship,demand_sum=dem,long_service=np.divide(roll(g.shipped,long,np.sum),dd,out=np.full(len(g),np.nan),where=dd!=0),service=np.divide(ship,dem,out=np.full(len(g),np.nan),where=dem!=0))
  elif f==2:
   mean=roll(x,k,np.mean,True);second_moment=roll(x*x,k,np.mean,True);variance=second_moment-mean*mean;score=np.zeros(len(g));good=variance>1e-12;score[good]=(x[good]-mean[good])/np.sqrt(variance[good]);out.update(baseline=mean,second_moment=second_moment,n=np.minimum(np.arange(len(g)),k),anomaly=score)
  elif f==3:out.update(variance=roll(x,k,np.var),volatility=roll(x,long,np.std),net_mean=roll(g.y,k,np.mean))
  elif f==4:
   t=g.day.to_numpy(float);mt=roll(t,k,np.mean);mx=roll(x,k,np.mean);mtx=roll(t*x,k,np.mean);mt2=roll(t*t,k,np.mean);den=mt2-mt*mt;slope=np.divide(mtx-mt*mx,den,out=np.zeros(len(g)),where=den>1e-12);out.update(mt=mt,mx=mx,mtx=mtx,mt2=mt2,slope=slope,prediction=mx+slope*(t-mt+h))
  elif f==5:out.update(lag1=lag(x,h),lag2=lag(x,h+2),history=roll(x,k,np.mean,True),past_revenue=roll(g.y,k,np.sum,True),momentum=x-lag(x,h))
  elif f==6:
   seasonal=np.empty(len(g))
   for ids in g.groupby('weekday').indices.values():seasonal[ids]=roll(x[ids],k,np.mean,True)
   residual=x-np.nan_to_num(seasonal);out.update(seasonal=seasonal,residual=residual,residual_mean=roll(residual,k,np.mean),residual_energy=roll(residual*residual,long,np.sum))
  elif f==11:
   correction=g.sensor.fillna(0).to_numpy()-g.original_sensor.to_numpy();out.update(sensor=g.sensor,original_sensor=g.original_sensor,correction=correction,rolling_correction=roll(correction,k,np.sum),current_last=g.sensor,observations=g.observations,raw_count=g.raw_count)
  elif f==13:
   dem=g.demand.to_numpy(float);active=roll((dem>0).astype(float),k,np.sum);out.update(calendar_mean=roll(dem,k,np.mean),active_mean=np.divide(roll(dem,k,np.sum),active,out=np.full(len(g),np.nan),where=active!=0),calendar_days=np.minimum(np.arange(len(g))+1,k+1),demand=dem,event_count=g.event_count)
  elif f==18:out.update(short_mean=roll(x,k,np.mean),long_mean=roll(x,long,np.mean),cumulative=np.cumsum(x),two_sided=[sum(x[max(0,j-k):min(len(g),j+h+1)]) for j in range(len(g))],momentum=roll(x,k,np.mean)-roll(x,long,np.mean))
  elif f==21:out.update(future_demand=[sum(g.demand.iloc[j+1:j+long+1]) if j+1<len(g) else np.nan for j in range(len(g))],causal_pressure=roll(x,k,np.mean,True));out['inventory_gap']=g.stock-np.asarray(out['future_demand'])
  elif f==33:
   sensor=g.sensor.to_numpy(float);earlier=lag(x,h);later=np.r_[x[h:],np.repeat(0.,h)];earlier[:h]=0;out.update(first_observed=[sensor[max(0,j-k)] for j in range(len(g))],last_observed=sensor,nth_observed=[sensor[max(0,j-k)+p['nth']-1] if min(j+1,k+1)>=p['nth'] else np.nan for j in range(len(g))],earlier=earlier,later=later)
  elif f in [35,37,41]:
   minute=g.minute.to_numpy();out['event_id']=g.event_id;out['minute']=minute;out['rn']=g.rn;rs=[];rc=[];excluded=[];selfex=[];cw=[]
   groups=np.unique(minute)
   for j in range(len(g)):
    mask=(minute>=minute[j]-p['range_min'])&(minute<=minute[j]);rs.append(x[mask].sum());rc.append(mask.sum());selfex.append(x[mask].sum()-x[j] if mask.sum()>1 else np.nan)
    if f==41:
     pos=np.searchsorted(groups,minute[j]);gm=(minute>=groups[max(0,pos-k)])&(minute<=minute[j]);gm&=(minute!=minute[j]);excluded.append(x[gm].sum()+x[j])
    if f==37:
     civil=g.civil_min.to_numpy();cw.append(x[(civil>=civil[j]-p['range_min'])&(civil<=civil[j])].sum())
   if f==35:out.update(rows_sum=roll(x,k,np.sum),range_sum=rs,rows_count=np.minimum(np.arange(len(g))+1,k+1),range_count=rc,time_mean=np.asarray(rs)/rc)
   elif f==41:out.update(peer_inclusive=rs,peer_excluded=excluded,excluding_self=selfex)
   else:out.update(civil_min=g.civil_min,previous_civil=g.civil_min.shift(),utc_gap=g.minute-g.prev_min,civil_gap=g.civil_min-g.civil_min.shift(),utc_window=rs,civil_window=cw)
  elif f in [38,39]:
   minute=g.minute.to_numpy();session=np.cumsum(np.r_[1,np.diff(minute)>p['gap']]);out.update(event_id=g.event_id,minute=minute,rn=g.rn,session_id=session);z=pd.DataFrame(dict(session=session,minute=minute,x=x,kind=g.kind));out['first_min']=z.groupby('session').minute.transform('min');out['last_min']=z.groupby('session').minute.transform('max');out['cumulative']=z.groupby('session').x.cumsum();out['session_rank']=z.groupby('session').cumcount()+1
   for phase in [0,1]:out[f'first_phase{phase}']=z.minute.where(z.kind==phase).groupby(z.session).transform(lambda v:v.expanding().min())
  elif f==43:
   sensor=g.sensor.to_numpy(float);observed=np.where(np.isnan(sensor),np.nan,g.day);observed=pd.Series(observed).ffill().to_numpy();out.update(observations=roll((~np.isnan(sensor)).astype(float),k,np.sum),null_count=roll(np.isnan(sensor).astype(float),k,np.sum),observed_last=sensor,last_day=observed,staleness=g.day-observed)
  frame=pd.DataFrame(out);rows.append(frame[frame.day>=p['d0']])
 full=pd.concat(rows,ignore_index=True) if rows else pd.DataFrame(columns=reference.columns);keys=['eid','minute','event_id'] if f in [35,37,38,39,41] else ['eid','day'];full=full.sort_values(keys).reset_index(drop=True)
 checked=[]
 for col in reference:
  if col in full:
   np.testing.assert_allclose(full[col].to_numpy(float),reference[col].to_numpy(float),rtol=1e-7,atol=1e-7,equal_nan=True,err_msg=f'native family={f} i={i} col={col}');checked.append(col)
 return {'native_window_columns':checked}

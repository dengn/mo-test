"""Demand-driven analysis; library implementation vs separately coded mathematical oracle."""
import math,itertools,warnings
import numpy as np,pandas as pd
from scipy import stats,linalg,special,optimize,sparse
from sklearn.linear_model import Ridge
from sklearn import metrics
import networkx as nx
from shapely.geometry import Point,LineString,box
from scenarios import params

def mean(x,ref=False):
 x=np.asarray(x,float);x=x[np.isfinite(x)]
 return math.fsum(float(v) for v in x)/len(x) if ref and len(x) else float(np.mean(x)) if len(x) else np.nan
def variance(x,ref=False,ddof=0):
 x=np.asarray(x,float);x=x[np.isfinite(x)]
 if len(x)<=ddof:return np.nan
 if not ref:return float(np.var(x,ddof=ddof))
 m=mean(x,True);return math.fsum((float(v)-m)**2 for v in x)/(len(x)-ddof)
def quantile(x,p,ref=False):
 x=np.asarray(x,float);x=x[np.isfinite(x)]
 if not len(x):return np.nan
 if not ref:return float(np.quantile(x,p))
 s=sorted(map(float,x));pos=(len(s)-1)*p;lo=int(math.floor(pos));hi=int(math.ceil(pos));return s[lo]*(hi-pos)+s[hi]*(pos-lo) if hi!=lo else s[lo]
def ridge(x,y,lam,ref):
 if ref:return linalg.solve(x.T@x+lam*np.eye(x.shape[1]),x.T@y,assume_a='pos')
 return Ridge(alpha=lam,fit_intercept=False).fit(x,y).coef_
def bh(p,ref=False):
 p=np.asarray(p,float)
 if not len(p):return p
 if not ref:return stats.false_discovery_control(p,method='bh')
 order=np.argsort(p,kind='stable');out=np.empty(len(p));running=1.
 for k in range(len(p)-1,-1,-1):running=min(running,p[order[k]]*len(p)/(k+1));out[order[k]]=running
 return out
def roll(x,k,ref=False):
 x=np.asarray(x,float)
 if ref:return np.array([mean(x[max(0,i-k+1):i+1],True) for i in range(len(x))])
 return pd.Series(x).rolling(k,min_periods=1).mean().to_numpy()
def matrix(rows,cols):return pd.DataFrame(rows,columns=cols.split())
def finite(v,default=0.):return float(v) if np.isfinite(v) else default

def point(d,j,p,ref):
 rows=[]
 for u,g in d.groupby('uid',sort=True):
  g=g.sort_values('day');r=g.iloc[-1];m=float(r.mean_val);v=float(r.var_val);n=float(r.n);nr=float(r.n_rows);scale=float(r.attr_scale)
  assert np.isnan(r.max_received) or r.max_received<=r.day
  assert np.isnan(r.recorded_day) or r.recorded_day<=r.day
  if j==0:a,b,c=m,np.sqrt(max(v,0)) if np.isfinite(v) else np.nan,float(r.val_sum)
  elif j==1:a,b,c=n/max(nr,1),nr-n,np.sqrt(max(v,0)/n) if n else np.nan
  elif j==2:a,b,c=m*scale,finite(r.max_val)-finite(r.min_val),float(pd.notna(r.aid))
  elif j==3:a,b,c=(finite(r.max_val)-finite(r.min_val))/p['lb'],np.sqrt(max(v,0)) if np.isfinite(v) else np.nan,m
  elif j==4:a,b,c=float(r.max_revision),m,float(r.max_received-r.day) if pd.notna(r.max_received) else np.nan
  elif j==5:a,b,c=float(r.max_received-r.day) if pd.notna(r.max_received) else np.nan,m,float(pd.isna(r.label_y))
  elif j in [6,9]:
   train=g[g.label_y.notna()];x=np.column_stack([np.ones(len(train)),train.mean_val.to_numpy(float)/30,train.attr_scale.to_numpy(float)])
   if len(train):coef=ridge(x,train.label_y.to_numpy(float),.1,ref);a=float(np.array([1,m/30,scale])@coef)
   else:a=m*scale
   b,c=float(len(train)),float(pd.isna(r.label_y))
  elif j==7:
   peers=d[d.day==r.day].mean_val.to_numpy(float);mu=mean(peers,ref);sd=np.sqrt(variance(peers,ref));a,b,c=(m-mu)/sd if sd>1e-12 else 0.,mu,sd
  else:a,b,c=nr,float(pd.notna(r.aid)),m
  rows.append([u,int(r.day),a,b,c,n])
 return matrix(rows,'uid day metric_a metric_b metric_c n')

def incremental(d,j,p,ref):
 rows=[]
 for u,g in d.groupby('uid',sort=True):
  g=g.sort_values('day');x=g.v.to_numpy(float);n=g.n.to_numpy(float);r=roll(x,p['k'],ref);total=math.fsum(map(float,x)) if ref else float(x.sum());mu=mean(x,ref);sd=np.sqrt(variance(x,ref))
  np.testing.assert_allclose(g.v,g.raw_total,rtol=1e-10,atol=1e-10);assert np.array_equal(g.n.to_numpy(),g.raw_n.to_numpy())
  if j==0:a,b,c=total,float(n.sum()),mu
  elif j==1:a,b,c=float(r[-1]),mean(r,ref),quantile(r,p['alpha'],ref)
  elif j==2:a,b,c=total,float(np.count_nonzero(n)),float((n==0).sum())
  elif j==3:a,b,c=float(x[-1]-x[0]),float(r[-1]-r[0]),mean(np.diff(x),ref)
  elif j==4:a,b,c=float(x.max()),float(x.min()),float(np.argmax(x))
  elif j==5:
   early=x[g.day.to_numpy()<=p['cut']-p['lb']//2];late=x[g.day.to_numpy()>p['cut']-p['lb']//2];a,b,c=mean(early,ref),mean(late,ref),mean(late,ref)-mean(early,ref)
  elif j==6:a,b,c=float((n==0).mean()),mu,float(len(x))
  elif j==7:a,b,c=(x[-1]-mu)/sd if sd>1e-12 else 0.,mu,sd
  elif j==8:a,b,c=total/(100+p['parameter']%90),float(np.maximum(np.cumsum(x)-(100+p['parameter']%90),0).sum()),total
  else:a,b,c=float(x[-1]),float(n[-1]),float(n.sum())
  rows.append([u,a,b,c,float(n.sum())])
 return matrix(rows,'uid metric_a metric_b metric_c n')

def streaming(d,j,p,ref):
 rows=[]
 for u in range(p['lo'],p['hi']+1):
  g=d[d.uid==u].sort_values(['event_min','event_id']);x=g.v.to_numpy(float);times=g.event_min.to_numpy(float);count=len(g);bucket=np.floor(times/(p['k']+2)).astype(int) if count else np.array([],int)
  if not count:rows.append([u,0.,0.,0.,0]);continue
  assert g.event_id.is_unique
  if j==0:a,b,c=float(x.sum()),float(len(set(bucket))),mean(x,ref)
  elif j==1:r=roll(x,p['k'],ref);a,b,c=float(r[-1]),mean(r,ref),variance(r,ref)
  elif j==2:a,b,c=float((g.event_min<g.batch*10).sum()),float(times.max()-times.min()),mean(x,ref)
  elif j==3:a,b,c=float(len(set(g.event_id))),float(g.event_id.sum()),float(x.sum())
  elif j==4:
   sizes=g.groupby('session_id').size().to_numpy(float);a,b,c=float(len(sizes)),float(sizes.max()),mean(sizes,ref)
  elif j==5:
   watermark=p['checkpoint']*10+6-[0,5,10,20,30][p['policy']];closed=(bucket+1)*(p['k']+2)<=watermark;a,b,c=float(x[closed].sum()),float(closed.sum()),float(watermark)
  elif j==6:a,b,c=float(x[g.kind.to_numpy()==p['template']%4].sum()),float((g.kind==1).sum()),mean(x,ref)
  elif j==7:
   kind=g.kind.to_numpy(int);changes=int(np.count_nonzero(np.diff(kind)));a,b,c=float(changes),float(changes/max(count-1,1)),float(len(set(kind)))
  elif j==8:a,b,c=float(np.isnan(x).sum()),float(g.prev_min.isna().sum()),mean(np.diff(times),ref)
  else:a,b,c=float(g.event_id.sum()),float(count),float(g.session_id.max())
  rows.append([u,a,b,c,count])
 return matrix(rows,'uid metric_a metric_b metric_c n')

def welch(y,t,ref):
 a=y[t==1];b=y[t==0]
 if len(a)<2 or len(b)<2:return np.nan,np.nan,np.nan
 diff=mean(a,ref)-mean(b,ref);va=variance(a,ref,1)/len(a);vb=variance(b,ref,1)/len(b);se=np.sqrt(va+vb);df=(va+vb)**2/(va*va/(len(a)-1)+vb*vb/(len(b)-1)) if va+vb>0 else np.inf
 z=stats.t.ppf(.975,df);return diff,se,float(z)
def beta_interval(a,b,ref):
 if not ref:return stats.beta.ppf([.025,.975],a,b)
 out=[]
 for p in [.025,.975]:
  lo,hi=0.,1.
  for _ in range(70):
   mid=(lo+hi)/2
   if special.betainc(a,b,mid)<p:lo=mid
   else:hi=mid
  out.append((lo+hi)/2)
 return np.array(out)
def causal(d,j,p,ref):
 if not len(d):return matrix([[0,np.nan,np.nan,np.nan,0]],'key estimate lower upper n')
 y=d.post_mean.to_numpy(float);pre=d.pre_mean.to_numpy(float);t=d.arm.to_numpy(int);prop=d.propensity.to_numpy(float);n=len(y)
 if j==0:est,se,z=welch(y,t,ref);return matrix([[0,est,est-z*se,est+z*se,n]],'key estimate lower upper n')
 if j==1:
  var=variance(pre,ref,1);cov=math.fsum((float(x)-mean(pre,True))*(float(v)-mean(y,True)) for x,v in zip(pre,y))/(n-1) if ref else float(np.cov(pre,y,ddof=1)[0,1]);theta=cov/var if var>1e-12 else 0.;adj=y-theta*(pre-mean(pre,ref));est,se,z=welch(adj,t,ref);return matrix([[0,est,est-z*se,est+z*se,n]],'key estimate lower upper n')
 if j==2:est,se,z=welch(y-pre,t,ref);return matrix([[0,est,est-z*se,est+z*se,n]],'key estimate lower upper n')
 if j==3:
  wt=t/prop;wc=(1-t)/(1-prop);est=float(np.sum(wt*y)/wt.sum()-np.sum(wc*y)/wc.sum());effective=(wt.sum()**2/(wt@wt)+wc.sum()**2/(wc@wc));return matrix([[0,est,effective,float(prop.min()),n]],'key estimate lower upper n')
 if j==4:
  a=np.flatnonzero(t==1);b=np.flatnonzero(t==0);diff=[]
  for i in a:
   if not len(b):continue
   if ref:chosen=min(b,key=lambda k:(abs(float(pre[i]-pre[k])),int(d.iloc[k].sid)))
   else:distance=np.abs(pre[b]-pre[i]);chosen=b[np.lexsort((d.iloc[b].sid.to_numpy(),distance))[0]]
   diff.append(y[i]-y[chosen])
  est=mean(diff,ref);return matrix([[0,est,variance(diff,ref,1),float(len(diff)),n]],'key estimate lower upper n')
 if j==5:
  x=np.column_stack([np.ones(n),t,pre-mean(pre,ref)]);coef=linalg.lstsq(x,y)[0] if ref else np.linalg.lstsq(x,y,rcond=None)[0];res=y-x@coef;bread=linalg.inv(x.T@x);clusters=d.uid.to_numpy(int);meat=np.zeros((3,3));unique=np.unique(clusters)
  for cl in unique:
   ix=clusters==cl;s=x[ix].T@res[ix];meat+=np.outer(s,s)
  cov=bread@meat@bread*(len(unique)/max(len(unique)-1,1))*((n-1)/max(n-3,1));se=np.sqrt(max(cov[1,1],0));return matrix([[0,float(coef[1]),float(coef[1]-1.96*se),float(coef[1]+1.96*se),n]],'key estimate lower upper n')
 if j==6:
  rng=np.random.default_rng(p['seed']);a=y[t==1];b=y[t==0];draws=[]
  if not len(a) or not len(b):return matrix([[0,np.nan,np.nan,np.nan,n]],'key estimate lower upper n')
  for _ in range(48):
   ia=rng.integers(len(a),size=len(a));ib=rng.integers(len(b),size=len(b));draws.append(mean(a[ia],ref)-mean(b[ib],ref))
  return matrix([[0,mean(a,ref)-mean(b,ref),quantile(draws,.025,ref),quantile(draws,.975,ref),n]],'key estimate lower upper n')
 if j==7:
  rows=[]
  for arm in [0,1]:
   q=d[d.arm==arm];s=int(q.successes.sum());total=int(q.n_post.sum());interval=beta_interval(1+s,1+total-s,ref);rows.append([arm,(1+s)/(2+total),float(interval[0]),float(interval[1]),total])
  return matrix(rows,'key estimate lower upper n')
 rows=[];ps=[]
 for segment,g in d.groupby('segment',sort=True):
  yy=g.post_mean.to_numpy(float);tt=g.arm.to_numpy(int);est,se,z=welch(yy,tt,ref);pv=float(2*stats.t.sf(abs(est/se),max(len(g)-2,1))) if np.isfinite(se) and se>0 else 1.;ps.append(pv);rows.append([int(segment),est,est-z*se if np.isfinite(se) else np.nan,est+z*se if np.isfinite(se) else np.nan,len(g)])
 out=matrix(rows,'key estimate lower upper n')
 if j==9:out['adjusted_p']=bh(ps,ref);out['reject']=(out.adjusted_p<.05).astype(int)
 return out

def shapley(channels,prob,ref):
 channels=sorted(channels);n=len(channels);out={c:0. for c in channels}
 if not n:return out
 def val(s):return 1-math.prod(1-prob[c] for c in s)
 if ref:
  fact=math.factorial
  for c in channels:
   other=[x for x in channels if x!=c]
   for k in range(n):
    weight=fact(k)*fact(n-k-1)/fact(n)
    for subset in itertools.combinations(other,k):out[c]+=weight*(val(subset+(c,))-val(subset))
 else:
  perms=list(itertools.permutations(channels))
  for perm in perms:
   seen=[];previous=0.
   for c in perm:seen.append(c);current=val(seen);out[c]+=(current-previous)/len(perms);previous=current
 return out

def attribution(d,j,p,ref):
 credits={k:0. for k in range(-1,6)};total=0.;paths=[];durations=[]
 for cid,g in d.groupby('cid',sort=True):
  r=g.iloc[0];touch=g[g.tid.notna()].sort_values(['touch_min','tid']);channels=touch.channel.astype(int).tolist();paths.append((channels,int(r.converted)))
  if not r.converted:continue
  revenue=float(r.revenue);total+=revenue
  if not channels:credits[-1]+=revenue;continue
  durations.append(float(r.conversion_min-touch.touch_min.iloc[0]))
  if j==0:w=np.zeros(len(channels));w[-1]=1
  elif j==1:w=np.zeros(len(channels));w[0]=1
  elif j in [2,7]:w=np.ones(len(channels))/len(channels)
  elif j==3:
   age=(r.conversion_min-touch.touch_min.to_numpy(float))/1440;w=np.array([math.exp(-math.log(2)*float(v)/p['k']) for v in age]) if ref else np.exp(-np.log(2)*age/p['k']);w/=w.sum()
  elif j==4:
   if len(channels)==1:w=np.ones(1)
   elif len(channels)==2:w=np.array([.5,.5])
   else:w=np.full(len(channels),.2/(len(channels)-2));w[0]=w[-1]=.4
  elif j==5:
   prob={c:.1+.08*c for c in set(channels)};s=shapley(set(channels),prob,ref);den=sum(s.values())
   for c,v in s.items():credits[c]+=revenue*v/den
   continue
  elif j==8:
   unique=set(channels)
   for c in unique:credits[c]+=revenue/len(unique)
   continue
  else:w=np.ones(len(channels))/len(channels)
  for c,v in zip(channels,w):credits[c]+=revenue*float(v)
 if j==6:
  def conversion_probability(remove=None):
   count=np.zeros((9,9));start,conv,drop=6,7,8
   for path,converted in paths:
    nodes=[start]+path+[conv if converted else drop]
    for a,b in zip(nodes[:-1],nodes[1:]):count[a,b]+=1
   q=np.zeros((7,7));b=np.zeros(7)
   for k in range(7):
    den=count[k].sum()
    if den:q[k]=count[k,:7]/den;b[k]=count[k,conv]/den
   if remove is not None:q[:,remove]=0;q[remove,:]=0;b[remove]=0
   if ref:
    result=np.zeros(7)
    for _ in range(1000):
     nxt=q@result+b
     if np.max(np.abs(nxt-result))<1e-13:break
     result=nxt
    return float(nxt[start])
   return float(linalg.solve(np.eye(7)-q,b)[start])
  base=conversion_probability();effect={c:max(0.,base-conversion_probability(c)) for c in range(6)};den=sum(effect.values())
  if den>1e-12:credits={**{-1:0.},**{c:total*effect[c]/den for c in range(6)}}
 elif j==9:
  quality=np.array([.1+.08*c for c in range(6)]);budget=100+p['parameter']%100
  if ref:
   lo,hi=1e-12,float(quality.max())
   for _ in range(90):mid=(lo+hi)/2;spend=np.maximum(1/mid-1/quality,0);lo,hi=(mid,hi) if spend.sum()>budget else (lo,mid)
   allocation=np.maximum(1/((lo+hi)/2)-1/quality,0)
  else:
   root=optimize.brentq(lambda z:np.maximum(1/z-1/quality,0).sum()-budget,1e-12,float(quality.max()));allocation=np.maximum(1/root-1/quality,0)
  assert abs(allocation.sum()-budget)<1e-6
  return matrix([[c,float(allocation[c]),float(np.log1p(quality[c]*allocation[c])),budget] for c in range(6)],'key allocation utility budget')
 assert abs(sum(credits.values())-total)<1e-6
 return matrix([[c,credits[c],total,mean(durations,ref) if j==7 else 0.] for c in sorted(credits)],'key credit total duration')

def design(days,cut,lb,variant,holiday=None):
 t=(np.asarray(days,float)-cut)/max(lb,1);columns=[np.ones(len(t)),t,np.sin(np.asarray(days)*2*np.pi/7),np.cos(np.asarray(days)*2*np.pi/7)]
 if variant==3:columns.extend([t*t,t*t*t])
 if variant==7:columns.extend([np.asarray(days)%7==0,np.zeros(len(t)) if holiday is None else holiday])
 return np.column_stack(columns).astype(float)
def forecast(d,j,p,ref):
 rows=[];basepred={};errors={}
 for uid,g in d.groupby('uid',sort=True):
  train=g[g.day<=p['cut']].sort_values('day');future=g[g.day>p['cut']].sort_values('day');days=train.day.to_numpy(int);y=train.demand.to_numpy(float);fd=future.day.to_numpy(int)
  if j==0 or j==8 and len(y)<p['lb']:
   pred=np.array([float(y[np.flatnonzero(days<=day-7)[-1]]) if np.any(days<=day-7) else mean(y,ref) for day in fd]);res=y-mean(y,ref)
  else:
   x=design(days,p['cut'],p['lb'],j,train.holiday.to_numpy(float));xx=design(fd,p['cut'],p['lb'],j,future.holiday.to_numpy(float))
   if j==2 and len(y)>4:
    x=np.column_stack([np.ones(len(y)-2),y[1:-1]/50,y[:-2]/50,days[2:]/100]);coef=ridge(x,y[2:],.02,ref);history=list(y);pred=[]
    for day in fd:val=float(np.array([1,history[-1]/50,history[-2]/50,day/100])@coef);pred.append(val);history.append(val)
    pred=np.array(pred);res=y[2:]-x@coef
   else:
    if j==9:
     w=np.exp((days-p['cut'])/(p['k']+1));sw=np.sqrt(w);coef=ridge(x*sw[:,None],y*sw,.02,ref)
    else:coef=ridge(x,y,.02,ref)
    pred=xx@coef;res=y-x@coef
  basepred[int(uid)]=pred;errors[int(uid)]=max(variance(res,ref),.01)
  for h,(day,prediction,truth) in enumerate(zip(fd,pred,future.demand),1):
   if j==6:low=prediction+quantile(res,.1,ref);high=prediction+quantile(res,.9,ref)
   else:spread=1.645*np.sqrt(max(variance(res,ref),.01));low=prediction-spread;high=prediction+spread
   rows.append([int(uid),int(day),float(prediction),float(low),float(high),float(truth)])
 out=matrix(rows,'uid day prediction lower upper truth')
 if j==4:
  metrics_rows=[]
  for uid,g in d.groupby('uid',sort=True):
   y=g[g.day<=p['cut']].demand.to_numpy(float);err=[]
   for k in range(max(7,len(y)-4),len(y)):
    forecast_value=y[k-7] if k>=7 else mean(y[:k],ref);err.append(float(y[k]-forecast_value))
   metrics_rows.append([uid,np.sqrt(mean(np.square(err),ref)),mean(np.abs(err),ref),len(err)])
  return matrix(metrics_rows,'uid rmse mae n')
 if j==5:
  # Reconcile independent unit/total forecasts through diagonal weighted least squares.
  units=sorted(basepred);s=np.vstack([np.eye(len(units)),np.ones(len(units))]);w=np.diag([errors[u] for u in units]+[sum(errors.values())*.8]);new=[]
  for h in range(p['h']):
   bottom=np.array([basepred[u][h] for u in units]);upper=float(bottom.sum()*1.015);b=np.r_[bottom,upper]
   if ref:
    wi=linalg.inv(w);reconciled=linalg.solve(s.T@wi@s,s.T@wi@b,assume_a='pos')
   else:reconciled=np.linalg.lstsq(np.linalg.solve(linalg.sqrtm(w).real,s),np.linalg.solve(linalg.sqrtm(w).real,b),rcond=None)[0]
   for u,v in zip(units,reconciled):new.append([u,p['cut']+h+1,float(v),float(reconciled.sum()),float(upper)])
  return matrix(new,'uid day prediction coherent_total unreconciled_total')
 return out

def temporal_paths(d,root,depth,gap,ref):
 if not len(d):return []
 groups={int(k):list(g.sort_values(['minute','fid']).itertuples()) for k,g in d.groupby('src')};out=[]
 if ref:
  queue=[(root,-1e30,0.,[root],0)]
  while queue:
   node,time,amount,path,hops=queue.pop(0)
   if hops>=depth:continue
   for r in groups.get(node,[]):
    if r.minute>time and (hops==0 or r.minute-time<=gap):
     new=(r.dst,r.minute,amount+r.amount,path+[r.dst],hops+1);out.append(new);queue.append(new)
 else:
  def walk(node,time,amount,path,hops):
   if hops>=depth:return
   for r in groups.get(node,[]):
    if r.minute>time and (hops==0 or r.minute-time<=gap):
     new=(r.dst,r.minute,amount+r.amount,path+[r.dst],hops+1);out.append(new);walk(*new)
  walk(root,-1e30,0.,[root],0)
 return out

def graph(d,j,p,ref):
 if j==5:return d.copy()
 nodes=sorted(set(d.src.astype(int))|set(d.dst.astype(int))) if len(d) else list(range(p['lo'],p['hi']+1));index={u:k for k,u in enumerate(nodes)};n=len(nodes)
 if j in [0,1,3]:
  rows=[];importance={u:0. for u in nodes}
  for root in range(p['lo'],p['hi']+1):
   paths=temporal_paths(d,root,2+(p['parameter']%2),240+p['k']*20,ref)
   if j==0:rows.append([root,float(len({r[0] for r in paths})),float(len(paths)),mean([r[2] for r in paths],ref)])
   elif j==1:
    cycles=[r for r in paths if r[0]==root];rows.append([root,float(len(cycles)),mean([r[2] for r in cycles],ref),float(sum(r[4] for r in cycles))])
   else:
    for path in paths:
     for node in path[3][1:-1]:importance[node]+=1/max(len(path[3])-2,1)
  if j==3:rows=[[u,importance[u],0.,0.] for u in nodes]
  return matrix(rows,'uid metric_a metric_b metric_c')
 weights=d.groupby(['src','dst']).amount.sum() if len(d) else pd.Series(dtype=float)
 if j==4:
  a=np.zeros((n,n))
  for (src,dst),w in weights.items():a[index[int(src)],index[int(dst)]]+=float(w)
  transition=np.divide(a,a.sum(axis=1)[:,None],out=np.full_like(a,1/n),where=a.sum(axis=1)[:,None]>0)
  if ref:pi=linalg.solve(np.eye(n)-.85*transition.T,np.full(n,.15/n))
  else:
   g=nx.DiGraph();g.add_nodes_from(nodes)
   for (src,dst),w in weights.items():g.add_edge(int(src),int(dst),weight=float(w))
   result=nx.pagerank(g,alpha=.85,max_iter=1000,tol=1e-13);pi=np.array([result[u] for u in nodes])
  assert abs(float(pi.sum())-1)<1e-9
  return matrix([[u,float(pi[index[u]]),n,0.] for u in nodes],'uid metric_a metric_b metric_c')
 if j==6:
  edge=[(int(src),int(dst),1/(float(w)+1)) for (src,dst),w in weights.items()];root=p['lo']
  if ref:
   dist={u:np.inf for u in nodes};dist[root]=0.
   for _ in range(max(n-1,1)):
    previous=dist.copy()
    for src,dst,cost in edge:dist[dst]=min(dist[dst],previous[src]+cost)
  else:
   g=nx.DiGraph();g.add_nodes_from(nodes)
   for src,dst,cost in edge:g.add_edge(src,dst,weight=cost)
   dist=nx.single_source_dijkstra_path_length(g,root)
  return matrix([[u,float(dist.get(u,np.inf)) if np.isfinite(dist.get(u,np.inf)) else np.nan,0.,0.] for u in nodes],'uid metric_a metric_b metric_c')
 if j==7:
  eligible=[(int(a),int(b)) for (a,b),w in weights.items() if w>=p['threshold']*100]
  if ref:
   parent={u:u for u in nodes}
   def find(u):
    while parent[u]!=u:u=parent[u]
    return u
   for a,b in eligible:
    aa,bb=find(a),find(b);parent[max(aa,bb)]=min(aa,bb)
   components={u:min(v for v in nodes if find(v)==find(u)) for u in nodes}
  else:
   g=nx.Graph();g.add_nodes_from(nodes);g.add_edges_from(eligible);components={u:min(c) for c in nx.connected_components(g) for u in c}
  return matrix([[u,components[u],float(sum(v==components[u] for v in components.values())),0.] for u in nodes],'uid key n metric_c')
 rows=[]
 for u in nodes:
  outgoing=d[d.src==u];incoming=d[d.dst==u];amounts=outgoing.groupby('dst').amount.sum().to_numpy(float);den=amounts.sum();share=amounts/den if den>0 else amounts;concentration=float(np.sum(share*share))
  if j==2:a,b,c=float(outgoing.dst.nunique()),float(incoming.src.nunique()),float(outgoing.amount.sum()-incoming.amount.sum())
  elif j==8:a,b,c=concentration,float(den),float(len(share))
  else:
   mid=p['cut']-p['lb']//2;a=float(outgoing[outgoing.day<=mid].amount.sum());b=float(outgoing[outgoing.day>mid].amount.sum());c=b-a
  rows.append([u,a,b,c])
 return matrix(rows,'uid metric_a metric_b metric_c')

def risk(d,j,p,ref):
 a=d.pivot(index='day',columns='uid',values='x_return').sort_index().dropna();x=a.to_numpy(float);assets=list(a);n=len(x);m=x.shape[1] if x.ndim==2 else 0
 if n<2 or m==0:return matrix([[0,np.nan,np.nan,np.nan,0]],'key metric_a metric_b metric_c n')
 mu=np.array([mean(x[:,k],ref) for k in range(m)])
 if ref:
  cov=np.zeros((m,m))
  for i in range(m):
   for k in range(m):cov[i,k]=math.fsum((float(r[i])-mu[i])*(float(r[k])-mu[k]) for r in x)/(n-1)
 else:cov=np.atleast_2d(np.cov(x,rowvar=False,ddof=1))
 cov=cov+np.eye(m)*1e-8;weight=np.arange(1,m+1,dtype=float)+(p['parameter']%3);weight/=weight.sum();alpha=p['alpha'];portfolio_mu=float(mu@weight);portfolio_sd=float(np.sqrt(weight@cov@weight))
 if j==0:
  if ref:
   from statistics import NormalDist
   z=NormalDist().inv_cdf(alpha);density=math.exp(-z*z/2)/math.sqrt(2*math.pi)
  else:z=stats.norm.ppf(alpha);density=stats.norm.pdf(z)
  return matrix([[0,-portfolio_mu+portfolio_sd*z,-portfolio_mu+portfolio_sd*density/(1-alpha),portfolio_sd,n]],'key metric_a metric_b metric_c n')
 rng=np.random.default_rng(p['seed']);samples=128+(p['parameter']%4)*32;z=rng.normal(size=(samples,m));factor=linalg.cholesky(cov,lower=True) if ref else np.linalg.cholesky(cov)
 if ref:sim=np.array([[mu[k]+math.fsum(float(zrow[v])*factor[k,v] for v in range(m)) for k in range(m)] for zrow in z])
 else:sim=mu+z@factor.T
 if j==7:sim=np.vstack([mu+z@factor.T,mu-z@factor.T])
 if j==3:sim=sim-np.sqrt(np.diag(cov))*p['threshold']
 loss=-(sim@weight)
 if j==2:loss=-(x@weight-p['threshold']*.01)
 if j==6:loss=-(sim@weight+.5*np.sum(sim*sim*weight*20,axis=1))
 var=quantile(loss,alpha,ref);tail=loss[loss>=var];cvar=mean(tail,ref)
 if j==4:return matrix([[assets[k],float(weight[k]),float((cov@weight)[k]*weight[k]/max(weight@cov@weight,1e-20)),float(mu[k]),n] for k in range(m)],'uid exposure variance_share expected_return n')
 if j==5:
  target=.002+(p['parameter']%5)*.0005;cap=1.5
  if ref:exposure=min(cap,target/cvar) if cvar>0 else cap
  else:
   result=optimize.linprog([-1.],A_ub=[[cvar]],b_ub=[target],bounds=[(0,cap)],method='highs');assert result.success;exposure=float(result.x[0])
  assert exposure*cvar<=target+1e-8
  return matrix([[0,exposure,exposure*cvar,target,n]],'key metric_a metric_b metric_c n')
 if j==8:
  contributions=[]
  for k in range(m):contributions.append(float(-mean(sim[loss>=var,k],ref)*weight[k]))
  assert abs(sum(contributions)-cvar)<1e-9
  return matrix([[assets[k],contributions[k],cvar,weight[k],n] for k in range(m)],'uid capital_share total_cvar exposure n')
 if j==9:
  estimates=[]
  for _ in range(32):draw=loss[rng.integers(len(loss),size=len(loss))];estimates.append(quantile(draw,alpha,ref))
  return matrix([[0,var,quantile(estimates,.025,ref),quantile(estimates,.975,ref),n]],'key metric_a metric_b metric_c n')
 return matrix([[0,var,cvar,mean(loss,ref),n]],'key metric_a metric_b metric_c n')

def haversine(lat1,lon1,lat2,lon2,ref):
 if ref:
  a,b,c,e=map(math.radians,[lat1,lon1,lat2,lon2]);v=math.sin((c-a)/2)**2+math.cos(a)*math.cos(c)*math.sin((e-b)/2)**2;return 6371.*2*math.asin(math.sqrt(min(1,max(0,v))))
 a,b,c,e=np.radians([lat1,lon1,lat2,lon2]);v=np.sin((c-a)/2)**2+np.cos(a)*np.cos(c)*np.sin((e-b)/2)**2;return float(6371.*2*np.arcsin(np.sqrt(np.clip(v,0,1))))
def segment_box(x0,y0,x1,y1,bounds):
 # Liang-Barsky clipping, including endpoint/tangent contact.
 xmin,ymin,xmax,ymax=bounds;dx=x1-x0;dy=y1-y0;lo,hi=0.,1.
 for den,num in [(-dx,x0-xmin),(dx,xmax-x0),(-dy,y0-ymin),(dy,ymax-y0)]:
  if den==0:
   if num<0:return False
  else:
   t=num/den
   if den<0:lo=max(lo,t)
   else:hi=min(hi,t)
 if lo>hi:return False
 return True

def spatial(d,j,p,ref,context):
 fences=context['fences'];roads=context['roads'];rows=[]
 if j==7:
  size=.005*p['k'];groups={}
  for r in d.itertuples():
   x,y=math.floor(r.lon/size),math.floor(r.lat/size);groups[(x,y)]=groups.get((x,y),0)+1
  return matrix([[x,y,n] for (x,y),n in sorted(groups.items())],'grid_x grid_y n')
 if j==6:
  a=roads[roads.blocked_day>p['cut']];nodes=range(1,33);edge=[(int(r.src),int(r.dst),float(r.distance)*(1+p['threshold'])) for r in a.itertuples()];root=p['lo']
  if ref:
   dist={k:np.inf for k in nodes};dist[root]=0.
   for _ in range(31):
    previous=dist.copy()
    for src,dst,cost in edge:dist[dst]=min(dist[dst],previous[src]+cost)
  else:
   g=nx.DiGraph();g.add_nodes_from(nodes);g.add_weighted_edges_from(edge);dist=nx.single_source_dijkstra_path_length(g,root)
  return matrix([[u,float(dist.get(u,np.inf)) if np.isfinite(dist.get(u,np.inf)) else np.nan] for u in nodes],'uid distance')
 if j==5:
  bybucket={};threshold=.5+p['k']*.5
  for r in d.itertuples():bybucket.setdefault(int(r.minute//35),[]).append(r)
  for key,points in sorted(bybucket.items()):
   hits=0;nearest=np.inf
   for a,b in itertools.combinations(points,2):
    if a.uid==b.uid:continue
    distance=haversine(a.lat,a.lon,b.lat,b.lon,ref);nearest=min(nearest,distance);hits+=distance<=threshold
   rows.append([key,hits,nearest if np.isfinite(nearest) else np.nan])
  return matrix(rows,'key n distance')
 for uid,g in d.groupby('uid',sort=True):
  g=g.sort_values(['minute','pid']);dist=[];speeds=[]
  for r in g.itertuples():
   if pd.isna(r.prev_lat) or pd.isna(r.prev_min):continue
   km=haversine(r.prev_lat,r.prev_lon,r.lat,r.lon,ref);dt=r.minute-r.prev_min;dist.append(km);speeds.append(km*60/dt if dt>0 else np.nan)
  if j in [0,1,2,3]:
   for f in fences[fences.region==int(g.region.iloc[0])].itertuples():
    bounds=(f.x1,f.y1,f.x2,f.y2);polygon=box(*bounds);hits=0;duration=0
    for r in g.itertuples():
     if j==0:inside=(f.x1<r.lon<f.x2 and f.y1<r.lat<f.y2) if ref else polygon.contains(Point(r.lon,r.lat))
     else:inside=(f.x1<=r.lon<=f.x2 and f.y1<=r.lat<=f.y2) if ref else polygon.covers(Point(r.lon,r.lat))
     if j==2 and pd.notna(r.prev_lat):inside=segment_box(r.prev_lon,r.prev_lat,r.lon,r.lat,bounds) if ref else polygon.intersects(LineString([(r.prev_lon,r.prev_lat),(r.lon,r.lat)]))
     hits+=bool(inside)
     if inside and pd.notna(r.prev_min):duration+=max(0,min(r.minute-r.prev_min,120))
    rows.append([uid,f.fid,float(hits),float(duration),len(g)])
  elif j==4:rows.append([uid,0,float(sum(np.isfinite(x) and x>20+p['threshold']*70 for x in speeds)),quantile(speeds,.95,ref),len(g)])
  elif j==8:rows.append([uid,0,math.fsum(dist) if ref else float(np.sum(dist)),float(max(dist)) if dist else 0.,len(g)])
  else:
   counts=g.groupby('local_min').minute.nunique();duplicates=float(np.maximum(counts.to_numpy()-1,0).sum());rows.append([uid,0,duplicates,float(g.fold.sum()),len(g)])
 return matrix(rows,'uid key metric_a metric_b n')

def auc(y,prob,ref):
 if len(np.unique(y))<2:return np.nan
 if not ref:return float(metrics.roc_auc_score(y,prob))
 positive=prob[y==1];negative=prob[y==0];return math.fsum(float(a>b)+.5*float(a==b) for a in positive for b in negative)/(len(positive)*len(negative))
def monitoring(d,j,p,ref):
 y=d.label.to_numpy(float);prob=d.prob.to_numpy(float);known=np.isfinite(y);yy=y[known];pp=prob[known];n=len(yy)
 if j==0:return matrix([[0,auc(yy,pp,ref),float(yy.mean()) if n else np.nan,float(len(d)-n),n]],'key metric_a metric_b metric_c n')
 if j==1:
  bins=5+p['k'];bucket=np.minimum((pp*bins).astype(int),bins-1);rows=[];ece=0.
  for k in range(bins):
   mask=bucket==k;count=int(mask.sum());pr=mean(pp[mask],ref);rate=mean(yy[mask],ref);ece+=count/max(n,1)*abs(pr-rate) if count else 0.;rows.append([k,count,pr,rate])
  out=matrix(rows,'key n predicted observed');out['ece']=ece;return out
 if j==2:
  clipped=np.clip(pp,1e-6,1-1e-6);brier=mean((pp-yy)**2,ref);loss=mean([-float(a)*math.log(float(b))-(1-float(a))*math.log(1-float(b)) for a,b in zip(yy,clipped)],True) if ref else float(metrics.log_loss(yy,clipped,labels=[0,1])) if n else np.nan
  return matrix([[0,brier,loss,0.,n]],'key metric_a metric_b metric_c n')
 if j in [3,8]:
  rows=[]
  cohorts=list(d.groupby('segment',sort=True)) if j==3 else [(int(k),d) for k in range(5)]
  for key,g in cohorts:
   threshold=p['threshold'] if j==3 else .1+key*.2;valid=g.label.notna();label=g.loc[valid,'label'].to_numpy(int);score=g.loc[valid,'prob'].to_numpy(float);pred=score>=threshold;tp=int(np.sum(pred&(label==1)));fp=int(np.sum(pred&(label==0)));pos=int(np.sum(label==1));neg=int(np.sum(label==0));rows.append([key,tp/max(pos,1),fp/max(neg,1),tp/max(tp+fp,1),len(label)])
  return matrix(rows,'key tpr fpr precision n')
 if j in [4,5]:
  feature=d.feature.to_numpy(float);early=feature[d.day.to_numpy()<=p['cut']-p['lb']//2];late=feature[d.day.to_numpy()>p['cut']-p['lb']//2]
  if not len(early) or not len(late):return matrix([[0,np.nan,np.nan,0.,len(d)]],'key metric_a metric_b metric_c n')
  if j==4:
   edges=np.linspace(-4,4,9);a=np.histogram(np.clip(early,-3.999,3.999),edges)[0].astype(float)+.5;b=np.histogram(np.clip(late,-3.999,3.999),edges)[0].astype(float)+.5;a/=a.sum();b/=b.sum();psi=math.fsum((float(x)-float(y))*math.log(float(x/y)) for x,y in zip(a,b)) if ref else float(np.sum(special.rel_entr(a,b)+special.rel_entr(b,a)));return matrix([[0,psi,float(len(early)),float(len(late)),len(d)]],'key metric_a metric_b metric_c n')
  if ref:
   points=sorted(set(early)|set(late));ks=max(abs(sum(a<=x for a in early)/len(early)-sum(b<=x for b in late)/len(late)) for x in points)
  else:ks=float(stats.ks_2samp(early,late).statistic)
  critical=1.36*np.sqrt((len(early)+len(late))/(len(early)*len(late)));return matrix([[0,ks,float(critical),float(ks>critical),len(d)]],'key metric_a metric_b metric_c n')
 if j==6:
  a=d.feature.to_numpy(float);b=d.prob.to_numpy(float)
  if ref:
   ma,mb=mean(a,True),mean(b,True);cross=math.fsum((float(x)-ma)*(float(y)-mb) for x,y in zip(a,b));den=np.sqrt(math.fsum((float(x)-ma)**2 for x in a)*math.fsum((float(y)-mb)**2 for y in b));cor=cross/den if den>1e-15 else np.nan
  else:cor=float(np.corrcoef(a,b)[0,1]) if len(a)>1 and np.std(a)>0 and np.std(b)>0 else np.nan
  return matrix([[0,cor,mean(a,ref),mean(b,ref),len(a)]],'key metric_a metric_b metric_c n')
 if j==7:
  now=d.backfill_label.to_numpy(float);valid=np.isfinite(now);before=auc(yy,pp,ref);after=auc(now[valid],prob[valid],ref);return matrix([[0,before,after,float(valid.sum()-known.sum()),len(d)]],'key metric_a metric_b metric_c n')
 rows=[];ps=[]
 for segment,g in d[d.label.notna()].groupby('segment',sort=True):
  successes=int(((g.prob>=p['threshold']).astype(int)==g.label).sum());total=len(g);p0=.6
  if ref:
   mass=lambda k:math.comb(total,k)*p0**k*(1-p0)**(total-k);observed=mass(successes);pv=min(1.,math.fsum(mass(k) for k in range(total+1) if mass(k)<=observed*(1+1e-7)))
  else:pv=float(stats.binomtest(successes,total,p0).pvalue)
  ps.append(pv);rows.append([int(segment),successes,total,pv])
 out=matrix(rows,'key successes n p_value');out['adjusted_p']=bh(ps,ref);out['reject']=(out.adjusted_p<.05).astype(int);return out

FUNCTIONS=[point,incremental,streaming,causal,attribution,forecast,graph,risk,spatial,monitoring]
def analyze(domain,j,i,data,oracle=False,context=None):
 p=params(domain,j,i)
 with warnings.catch_warnings():
  warnings.simplefilter('ignore');result=FUNCTIONS[domain](data,j,p,oracle,context) if domain==8 else FUNCTIONS[domain](data,j,p,oracle)
 return result.reset_index(drop=True)

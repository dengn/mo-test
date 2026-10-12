"""Raw-data selectors independent of SQL; mathematical references live in analytics.py."""
import functools
import numpy as np,pandas as pd
from scenarios import params
from data import EPOCH
class Native:
 def __init__(self,data):
  self.data=data;self.obs={int(u):g for u,g in data['observations'].groupby('uid')};self.attrs={int(u):g for u,g in data['attrs'].groupby('uid')};self.labels={(int(r.uid),int(r.day)):(float(r.y),int(r.ready_day)) for r in data['labels'].itertuples()}
  self.cache={};self.states={}
 def set_state(self,checkpoint,inc,accepted):self.states[checkpoint]=(inc,accepted)
 def expected(self,d,j,i):
  p=params(d,j,i);key=(d,j,i)
  if key in self.cache:return self.cache[key].copy()
  result=self._expected(d,j,p)
  # Avoid an unbounded output cache across 100000 queries.
  if len(self.cache)>2000:self.cache.clear()
  self.cache[key]=result.copy();return result
 def _expected(self,d,j,p):
  data=self.data;lo,hi,cut,lb,h=[p[k] for k in ['lo','hi','cut','lb','h']]
  if d==0:
   rows=[];anchors=range(cut-4,cut+1) if j in [6,9] else [cut]
   for u in range(lo,hi+1):
    for day in anchors:
     m=self.obs[u];m=m[(m.day>=day-lb)&(m.day<day)&(m.received_day<=day)].sort_values(['event_id','revision','rid']).drop_duplicates('event_id',keep='last');m=m[m.valid==1];v=m.v.dropna().to_numpy(float)
     a=self.attrs[u];a=a[(a.valid_from<=day)&(a.valid_to>day)&(a.recorded_day<=day)].sort_values(['recorded_day','revision','aid']);ar=a.iloc[-1] if len(a) else None
     lab=self.labels.get((u,day+h));known=lab is not None and lab[1]<=cut
     rows.append([u,day,u%4,len(v),len(m),float(v.sum()) if len(v) else np.nan,float(v.mean()) if len(v) else np.nan,float(v.var()) if len(v) else np.nan,float(v.min()) if len(v) else np.nan,float(v.max()) if len(v) else np.nan,float(m.received_day.max()) if len(m) else np.nan,float(m.revision.max()) if len(m) else np.nan,float(ar.aid) if ar is not None else np.nan,float(ar.recorded_day) if ar is not None else np.nan,float(ar.scale) if ar is not None else 1.,lab[0] if known else np.nan,lab[1] if known else np.nan])
   return pd.DataFrame(rows,columns='uid day region n n_rows val_sum mean_val var_val min_val max_val max_received max_revision aid recorded_day attr_scale label_y ready_day'.split())
  if d==1:
   inc,_=self.states[p['checkpoint']];g=inc.groupby(['uid','day']).v.agg(['sum','count']);rows=[]
   for u in range(lo,hi+1):
    for day in range(cut-lb,cut+1):
     key=(u,day);s=float(g.loc[key,'sum']) if key in g.index else 0.;n=int(g.loc[key,'count']) if key in g.index else 0;rows.append([u,day,s,n,s,n,day%7])
   return pd.DataFrame(rows,columns='uid day v n raw_total raw_n weekday'.split())
  if d==2:
   _,accepted=self.states[p['checkpoint']];end=p['checkpoint']*10+6;a=accepted[(accepted.policy==p['policy'])&(accepted.uid.between(lo,hi))&(accepted.event_min.between(end-lb*2,end))].sort_values(['uid','event_min','event_id']);rows=[]
   for u,g in a.groupby('uid',sort=True):
    prev=None;session=0
    for r in g.itertuples():
     if prev is None or r.event_min-prev>p['k']:session+=1
     rows.append([r.event_id,u,r.event_min,r.batch,r.v,r.kind,prev,session]);prev=r.event_min
   return pd.DataFrame(rows,columns='event_id uid event_min batch v kind prev_min session_id'.split())
  if d==3:
   s=data['subjects'];s=s[(s.uid.between(lo,hi))&((s.sid>384) if j in [3,4] else (s.sid<=384))];o=data['outcomes'];o=o[(o.ready_day<=cut)&o.day.between(8,cut)];rows=[]
   groups={int(sid):g for sid,g in o.groupby('sid')}
   for r in s.sort_values('sid').itertuples():
    g=groups.get(r.sid)
    if g is None:continue
    pre=g[g.day<32];post=g[g.day>=32]
    rows.append([r.sid,r.uid,r.segment,r.arm,r.propensity,r.age,r.pre,float(pre.y.mean()),float(post.y.mean()),len(pre),len(post),int(post.converted.sum())])
   return pd.DataFrame(rows,columns='sid uid segment arm propensity age pre pre_mean post_mean n_pre n_post successes'.split())
  if d==4:
   c=data['conversions'];c=c[c.person.between(lo,hi)&c.day.between(cut-lb,cut)];t=data['touches'];ident=data['identities'];known=set(ident[ident.recorded_day<=cut].device);t=t[(t.received_day<=cut)&t.device.isin(known)];tg={int(v):g for v,g in t.groupby('person')};camp=data['campaigns'].set_index('channel');rows=[]
   for r in c.sort_values('cid').itertuples():
    q=tg.get(r.person);q=q[q.minute.between(r.minute-lb*1440,r.minute)].sort_values(['minute','tid']) if q is not None else pd.DataFrame()
    if not len(q):rows.append([r.cid,r.person,r.day,r.minute,r.revenue,r.converted,np.nan,np.nan,np.nan,np.nan,np.nan,np.nan])
    else:
     for touch in q.itertuples():rows.append([r.cid,r.person,r.day,r.minute,r.revenue,r.converted,touch.tid,touch.channel,touch.minute,touch.score,float(camp.loc[touch.channel,'spend']),float(camp.loc[touch.channel,'quality'])])
   return pd.DataFrame(rows,columns='cid person day conversion_min revenue converted tid channel touch_min score spend quality'.split())
  if d==5:
   a=data['daily'];a=a[a.uid.between(lo,hi)&a.day.between(cut-lb,cut+h)].copy();a['region']=a.uid%4;a['weekday']=a.day%7;a['holiday']=((a.day%17==0)|(a.day%23==0)).astype(int);a['train_flag']=(a.day<=cut).astype(int)
   return a['uid day region weekday holiday signal demand price weather train_flag'.split()].sort_values(['uid','day']).reset_index(drop=True)
  if d==6:
   f=data['flows'];f=f[f.day.between(cut-lb,cut)&(f.received_day<=cut)].copy()
   if j==5:
    depth=2+(p['parameter']%2);gap=240+p['k']*20;groups={int(v):list(g.itertuples()) for v,g in f.groupby('src')};rows=[]
    def walk(node,minute,amount,hops,code):
     rows.append([lo,node,minute,amount,hops,code])
     if hops>=depth:return
     for r in groups.get(node,[]):
      if minute<r.minute<=minute+gap:walk(r.dst,r.minute,amount+r.amount,hops+1,code*33+r.dst)
    for r in groups.get(lo,[]):walk(r.dst,r.minute,r.amount,1,lo*33+r.dst)
    return pd.DataFrame(rows,columns='uid node last_min amount hops code'.split()).sort_values(['last_min','code','hops','amount']).reset_index(drop=True)
   f=f[f.src.between(lo,hi)|f.dst.between(lo,hi)];f['region']=f.src%4;f['sector']=f.src%5
   return f['fid src dst day minute amount region sector'.split()].sort_values(['minute','fid']).reset_index(drop=True)
  if d==7:
   a=data['daily'];a=a[a.uid.between(lo,min(32,lo+3))&a.day.between(cut-lb,cut)].copy().sort_values(['uid','day']);a['region']=a.uid%4;a['x_return']=a.groupby('uid').price.transform(lambda s:np.log(s/s.shift(1)))
   return a['uid day price signal weather region x_return'.split()].reset_index(drop=True)
  if d==8:
   a=data['gps'];a=a[a.uid.between(lo,hi)&a.day.between(cut-lb,cut)&(a.received_day<=cut)&(a.valid==1)].copy().sort_values(['uid','minute','pid']);a['region']=a.uid%4
   for field in ['lat','lon','minute']:a['prev_'+('min' if field=='minute' else field)]=a.groupby('uid')[field].shift(1)
   return a['pid uid day minute lat lon offset_min local_min fold region prev_lat prev_lon prev_min'.split()].reset_index(drop=True)
  if d==9:
   a=data['predictions'];a=a[a.uid.between(lo,hi)&a.day.between(cut-lb,cut)&(a.model==j%2)].copy().sort_values(['day','pid']);a['backfill_label']=a.label.where(a.ready_day<=cut+3);a['label']=a.label.where(a.ready_day<=cut)
   return a['pid uid day model segment prob label ready_day feature backfill_label'.split()].reset_index(drop=True)
  raise ValueError(d)

"""Real CPU deep training, train-only preprocessing, independent NumPy inference."""
import copy,hashlib,io,json,math
import numpy as np,torch
from torch import nn
from data import params
torch.set_num_threads(1);torch.set_num_interop_threads(1)
torch.use_deterministic_algorithms(True)
ARCH=['residual','temporal_cnn','gru','attention','gcn']
TASK=['forecast','classification','multitask','denoising']
FEATURES=['x0','x1','x2','x3','lag0','amt','ev','maintenance','outage','temp','weekday','price','exposure','cap','degree','bias','sector','region']
MISSIONS=[dict(id=a*4+t,architecture=arch,task=task) for a,arch in enumerate(ARCH) for t,task in enumerate(TASK)]
def prepared(f,i,edges):
 p=params(i);N=64;L=p['length'];x=f[FEATURES].to_numpy(np.float32).reshape(N,L,-1).astype(np.float64)
 # Quantization to float32 is the declared training-input contract, AFTER raw checks.
 ids=f.eid.to_numpy(np.int64).reshape(N,L)[:,0];sp=f.split_id.to_numpy(np.int64).reshape(N,L)[:,0];anchor=f.anchor.to_numpy(np.int64).reshape(N,L)[:,0]
 assert np.array_equal(sp,np.repeat([0,1,2],[40,12,12])) and len(np.unique(ids))==64
 assert anchor[:40].max()+p['horizon']<anchor[40:52].min() and anchor[40:52].max()+p['horizon']<anchor[52:].min()
 assert np.all(f.day.to_numpy().reshape(N,L)<=anchor[:,None])
 rr=np.random.default_rng(910000+i);mask=rr.random(x.shape)<p['missing']*.015;x[mask]=np.nan
 x[:,:,:4]+=rr.normal(0,p['noise'],(N,L,4))
 median=np.nanmedian(x[:40].reshape(-1,len(FEATURES)),axis=0);x=np.ascontiguousarray(np.where(np.isnan(x),median,x))
 mu=x[:40].mean((0,1));sd=x[:40].std((0,1));sd=np.where(sd<1e-10,1,sd);z=np.clip((x-mu)/sd,-8,8).astype(np.float32)
 # Independently rebuild imputation/standardization using columns and training rows.
 flat=x.reshape(-1,len(FEATURES));mn=np.array([flat[:40*L,k].mean() for k in range(len(FEATURES))]);st=np.array([flat[:40*L,k].std() for k in range(len(FEATURES))]);st[st<1e-10]=1
 assert np.allclose(mu,mn,rtol=1e-12,atol=1e-12) and np.allclose(sd,st,rtol=1e-12,atol=1e-12)
 # Holdout perturbation cannot change training-fitted statistics.
 mutated=x.copy();mutated[40:]=1e6
 assert np.array_equal(mu,mutated[:40].mean((0,1)))
 last=f.groupby('eid',sort=True).tail(1);y=last[['response','risk','anomaly','c0','c1','c2','c3']].to_numpy(np.float32)
 ym=np.r_[y[:40,0].mean(),y[:40,3:].mean(0)];ys=np.r_[y[:40,0].std(),y[:40,3:].std(0)];ys=np.where(ys<1e-8,1,ys)
 adj=np.eye(N,dtype=np.float32);idx={int(v):k for k,v in enumerate(ids)}
 for src,dst,w in edges.itertuples(index=False,name=None):
  if int(src) in idx and int(dst) in idx and sp[idx[int(src)]]==sp[idx[int(dst)]]:adj[idx[int(src)],idx[int(dst)]]+=w
 adj/=adj.sum(1,keepdims=True);assert np.allclose(adj.sum(1),1) and np.all(adj[sp[:,None]!=sp[None,:]]==0)
 return dict(x=z,y=y,mu=mu,sd=sd,median=median,ym=ym,ys=ys,adj=adj,ids=ids,sp=sp,anchor=anchor)
class Residual(nn.Module):
 def __init__(self,h):super().__init__();self.a=nn.Linear(h,h);self.b=nn.Linear(h,h)
 def forward(self,x):return torch.relu(x+self.b(torch.relu(self.a(x))))
class Attention(nn.Module):
 def __init__(self,h):
  super().__init__();self.att=nn.MultiheadAttention(h,2,batch_first=True,dropout=0);self.norm1=nn.LayerNorm(h);self.norm2=nn.LayerNorm(h);self.a=nn.Linear(h,h*2);self.b=nn.Linear(h*2,h)
 def forward(self,x):
  v=self.att(x,x,x,need_weights=False)[0];x=self.norm1(x+v);return self.norm2(x+self.b(torch.relu(self.a(x))))
class Net(nn.Module):
 def __init__(self,arch,task,p):
  super().__init__();self.arch=arch;self.task=task;h=p['hidden'];d=p['depth'];F=len(FEATURES);out={'forecast':1,'classification':1,'multitask':2,'denoising':4}[task]
  if arch=='residual':self.proj=nn.Linear(F*3,h);self.blocks=nn.ModuleList([Residual(h) for _ in range(d)])
  elif arch=='temporal_cnn':self.blocks=nn.ModuleList([nn.Conv1d(F if j==0 else h,h,3,padding=1) for j in range(d)])
  elif arch=='gru':self.gru=nn.GRU(F,h,num_layers=d,batch_first=True);self.proj=nn.Linear(h,h)
  elif arch=='attention':self.proj=nn.Linear(F,h);self.blocks=nn.ModuleList([Attention(h) for _ in range(d)])
  elif arch=='gcn':self.proj=nn.Linear(F*2,h);self.blocks=nn.ModuleList([nn.Linear(h,h) for _ in range(d)])
  self.head=nn.Linear(h,out)
 def forward(self,x,adj):
  if self.arch=='residual':
   z=torch.relu(self.proj(torch.cat([x[:,-1],x.mean(1),x.std(1,unbiased=False)],1)))
   for b in self.blocks:z=b(z)
  elif self.arch=='temporal_cnn':
   z=x.transpose(1,2)
   for b in self.blocks:z=torch.relu(b(z))
   z=z.mean(2)
  elif self.arch=='gru':z=torch.relu(self.proj(self.gru(x)[0][:,-1]))
  elif self.arch=='attention':
   z=self.proj(x);pos=torch.arange(x.shape[1],dtype=x.dtype,device=x.device)[:,None];freq=torch.arange(z.shape[-1],dtype=x.dtype,device=x.device)[None,:];z=z+torch.sin(pos/(1+freq))*.1
   for b in self.blocks:z=b(z)
   z=z.mean(1)
  else:
   z=torch.relu(self.proj(torch.cat([x[:,-1],x.mean(1)],1)))
   for b in self.blocks:z=torch.relu(b(adj@z)+z)
  return self.head(z)
def loss(pred,prep,task,sl):
 y=torch.from_numpy(prep['y']);ym=torch.tensor(prep['ym'],dtype=torch.float32);ys=torch.tensor(prep['ys'],dtype=torch.float32)
 if task=='forecast':return nn.functional.mse_loss(pred[sl,0],(y[sl,0]-ym[0])/ys[0])
 if task=='classification':return nn.functional.binary_cross_entropy_with_logits(pred[sl,0],y[sl,1])
 if task=='multitask':return nn.functional.mse_loss(pred[sl,0],(y[sl,0]-ym[0])/ys[0])+nn.functional.binary_cross_entropy_with_logits(pred[sl,1],y[sl,1])
 return nn.functional.mse_loss(pred[sl],(y[sl,3:]-ym[1:])/ys[1:])
def predict(m,p):
 m.eval()
 with torch.no_grad():return m(torch.from_numpy(p['x']),torch.from_numpy(p['adj'])).numpy()
def fit(p,mission,i):
 cfg=params(i);torch.manual_seed(730000+mission*1000+i);desc=MISSIONS[mission];m=Net(desc['architecture'],desc['task'],cfg)
 x=torch.from_numpy(p['x']);a=torch.from_numpy(p['adj']);opt=torch.optim.Adam(m.parameters(),lr=cfg['lr'],weight_decay=cfg['l2']);tr=np.arange(40);va=np.arange(40,52)
 with torch.no_grad():initial=float(loss(m(x,a),p,desc['task'],tr));best=float(loss(m(x,a),p,desc['task'],va))
 initial_weights=copy.deepcopy(m.state_dict());state=copy.deepcopy(initial_weights);history=[];bestepoch=0;maxgrad=0.;clipped=0;steps=0
 for epoch in range(cfg['epochs']):
  # Fixed, seeded mini-batch schedule, with full graph propagation restricted by split.
  rr=np.random.default_rng(500000+i+epoch);order=rr.permutation(tr)
  m.train()
  for j in range(0,40,cfg['batch']):
   opt.zero_grad();l=loss(m(x,a),p,desc['task'],order[j:j+cfg['batch']]);assert torch.isfinite(l);l.backward()
   for w in m.parameters():assert w.grad is not None and torch.isfinite(w.grad).all()
   gn=float(nn.utils.clip_grad_norm_(m.parameters(),cfg['clip']));assert math.isfinite(gn);maxgrad=max(maxgrad,gn);clipped+=gn>cfg['clip'];opt.step();steps+=1
  with torch.no_grad():pr=m(x,a);tl=float(loss(pr,p,desc['task'],tr));vl=float(loss(pr,p,desc['task'],va))
  assert math.isfinite(tl+vl);history.append([tl,vl])
  if vl<best:best=vl;state=copy.deepcopy(m.state_dict());bestepoch=epoch+1
 assert min(v[0] for v in history)<initial and maxgrad>0,('no_learning',initial,history)
 assert any(not torch.equal(w,initial_weights[k]) for k,w in m.state_dict().items()),'no_updates'
 m.load_state_dict(state);out=predict(m,p);assert np.isfinite(out).all()
 changed=dict(p);changed['y']=p['y'].copy();changed['y'][52:]=1e6
 check=torch.from_numpy(out)
 assert torch.equal(loss(check,p,desc['task'],tr),loss(check,changed,desc['task'],tr))
 assert torch.equal(loss(check,p,desc['task'],va),loss(check,changed,desc['task'],va))
 metrics=dict(initial_train_loss=initial,min_train_loss=min(v[0] for v in history),best_validation_loss=best,best_epoch=bestepoch,epochs=cfg['epochs'],steps=steps,max_gradient_norm=maxgrad,clipped_steps=clipped,history=history)
 return m,out,metrics
def linear(x,w,key):return x@w[key+'.weight'].T+w[key+'.bias']
def numpy_forward(m,p):
 w={k:v.detach().numpy().astype(float) for k,v in m.state_dict().items()};x=p['x'].astype(float);relu=lambda z:np.maximum(z,0);a=m.arch
 if a=='residual':
  z=relu(linear(np.concatenate([x[:,-1],x.mean(1),x.std(1)],1),w,'proj'))
  for j in range(len(m.blocks)):z=relu(z+linear(relu(linear(z,w,f'blocks.{j}.a')),w,f'blocks.{j}.b'))
 elif a=='temporal_cnn':
  z=x.transpose(0,2,1)
  for j in range(len(m.blocks)):
   ww=w[f'blocks.{j}.weight'];zz=np.pad(z,((0,0),(0,0),(1,1)));v=sum(np.einsum('nft,of->not',zz[:,:,k:k+z.shape[2]],ww[:,:,k]) for k in range(3));z=relu(v+w[f'blocks.{j}.bias'][None,:,None])
  z=z.mean(2)
 elif a=='gru':
  z=x
  for j in range(m.gru.num_layers):
   h=np.zeros((len(x),m.gru.hidden_size));outputs=[]
   for t in range(z.shape[1]):
    gi=z[:,t]@w[f'gru.weight_ih_l{j}'].T+w[f'gru.bias_ih_l{j}'];gh=h@w[f'gru.weight_hh_l{j}'].T+w[f'gru.bias_hh_l{j}'];ir,iz,inn=np.split(gi,3,1);hr,hz,hn=np.split(gh,3,1)
    r=1/(1+np.exp(-(ir+hr)));zz=1/(1+np.exp(-(iz+hz)));n=np.tanh(inn+r*hn);h=(1-zz)*n+zz*h;outputs.append(h)
   z=np.stack(outputs,1)
  z=relu(linear(z[:,-1],w,'proj'))
 elif a=='attention':
  z=linear(x,w,'proj');z+=np.sin(np.arange(x.shape[1])[:,None]/(1+np.arange(z.shape[-1])[None,:]))*.1
  for j in range(len(m.blocks)):
   pre=f'blocks.{j}';q,k,v=np.split(z@w[pre+'.att.in_proj_weight'].T+w[pre+'.att.in_proj_bias'],3,2);N,L,H=q.shape;dh=H//2
   q=q.reshape(N,L,2,dh).transpose(0,2,1,3);k=k.reshape(N,L,2,dh).transpose(0,2,1,3);v=v.reshape(N,L,2,dh).transpose(0,2,1,3)
   score=q@k.transpose(0,1,3,2)/math.sqrt(dh);score-=score.max(-1,keepdims=True);prob=np.exp(score);prob/=prob.sum(-1,keepdims=True);att=(prob@v).transpose(0,2,1,3).reshape(N,L,H);z+=linear(att,w,pre+'.att.out_proj')
   def norm(zz,key):return (zz-zz.mean(-1,keepdims=True))/np.sqrt(zz.var(-1,keepdims=True)+1e-5)*w[key+'.weight']+w[key+'.bias']
   z=norm(z,pre+'.norm1');z=norm(z+linear(relu(linear(z,w,pre+'.a')),w,pre+'.b'),pre+'.norm2')
  z=z.mean(1)
 else:
  z=relu(linear(np.concatenate([x[:,-1],x.mean(1)],1),w,'proj'))
  for j in range(len(m.blocks)):z=relu(linear(p['adj'].astype(float)@z,w,f'blocks.{j}')+z)
 return linear(z,w,'head')
def evaluate(out,p,task):
 y=p['y'];test=np.arange(52,64);val=np.arange(40,52);r={}
 if task in ['forecast','multitask']:
  prediction=out[:,0]*p['ys'][0]+p['ym'][0];res=np.abs(prediction[val]-y[val,0]);q=float(np.quantile(res,min(1,math.ceil((len(val)+1)*.8)/len(val)),method='higher'))
  r.update(rmse=float(np.sqrt(np.mean((prediction[test]-y[test,0])**2))),baseline_rmse=float(np.sqrt(np.mean((p['ym'][0]-y[test,0])**2))),mae=float(np.mean(np.abs(prediction[test]-y[test,0]))),interval_halfwidth=q,coverage=float(np.mean(np.abs(prediction[test]-y[test,0])<=q)))
 if task in ['classification','multitask']:
  logit=out[:,0 if task=='classification' else 1];prob=1/(1+np.exp(-np.clip(logit,-40,40)));assert np.all((prob>=0)&(prob<=1));candidates=np.linspace(.15,.85,15);cost=[np.mean((prob[val]>th)!=y[val,1]) for th in candidates];th=float(candidates[int(np.argmin(cost))]);r.update(accuracy=float(np.mean((prob[test]>th)==y[test,1])),brier=float(np.mean((prob[test]-y[test,1])**2)),threshold=th,positive_test=int(y[test,1].sum()))
 if task=='denoising':
  pred=out*p['ys'][1:]+p['ym'][1:];r.update(reconstruction_rmse=float(np.sqrt(np.mean((pred[test]-y[test,3:])**2))),anomalies_in_holdout=int(y[test,2].sum()))
 assert all(math.isfinite(v) for v in r.values());return r
def serialize(m):
 b=io.BytesIO();torch.save(m.state_dict(),b);return b.getvalue()
def reload(blob,mission,i):
 desc=MISSIONS[mission];m=Net(desc['architecture'],desc['task'],params(i));m.load_state_dict(torch.load(io.BytesIO(blob),map_location='cpu',weights_only=True));return m

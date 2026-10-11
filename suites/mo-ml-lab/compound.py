"""Supplementary 100 hybrid deep workflows: temporal + attention + graph + multi-head."""
import copy,hashlib,io,json,time
import numpy as np,torch
from torch import nn
from data import ROOT,connect,tables,native,read,query,compare
from models import prepared,Attention
class Hybrid(nn.Module):
 def __init__(self,h):
  super().__init__();self.conv=nn.ModuleList([nn.Conv1d(18 if j==0 else h,h,3,padding=1) for j in range(3)]);self.gru=nn.GRU(h,h,2,batch_first=True);self.att=nn.ModuleList([Attention(h) for _ in range(3)]);self.graph=nn.ModuleList([nn.Linear(h,h) for _ in range(3)]);self.drop=nn.Dropout(.1);self.head=nn.Sequential(nn.Linear(h,h),nn.ReLU(),nn.Linear(h,9))
 def forward(self,x,a):
  z=x.transpose(1,2)
  for b in self.conv:z=torch.relu(b(z))
  z=self.gru(z.transpose(1,2))[0]
  for b in self.att:z=b(z)
  z=z.mean(1)
  for b in self.graph:z=torch.relu(b(a@z)+z)
  return self.head(self.drop(z))
def ordered_quantiles(out):
 mid=out[:,6];return torch.stack([mid-nn.functional.softplus(out[:,7]),mid,mid+nn.functional.softplus(out[:,8])],1)
def objective(out,p,sl):
 y=torch.from_numpy(p['y']);target=(y[:,0]-float(p['ym'][0]))/float(p['ys'][0]);rec=torch.from_numpy(p['x'][:,-1,:4]);taus=torch.tensor([.1,.5,.9]);e=target[sl,None]-ordered_quantiles(out)[sl]
 return nn.functional.mse_loss(out[sl,0],target[sl])+nn.functional.binary_cross_entropy_with_logits(out[sl,1],y[sl,1])+.25*nn.functional.mse_loss(out[sl,2:6],rec[sl])+.4*torch.maximum(taus*e,(taus-1)*e).mean()
def fit_hybrid(p,i):
 seed=880000+i;torch.manual_seed(seed);h=16+8*(i%2);m=Hybrid(h);rr=np.random.default_rng(seed);mask=rr.random(p['x'].shape)<.12;masked=p['x'].copy();masked[mask]=0
 x=torch.from_numpy(masked);a=torch.from_numpy(p['adj']);tr=np.arange(40);va=np.arange(40,52);opt=torch.optim.AdamW(m.parameters(),lr=.004,weight_decay=.001);history=[];best=float('inf');state=None
 for ep in range(24):
  m.train();opt.zero_grad();l=objective(m(x,a),p,tr);assert torch.isfinite(l);l.backward();g=float(nn.utils.clip_grad_norm_(m.parameters(),1.0));assert np.isfinite(g)
  for w in m.parameters():assert w.grad is not None and torch.isfinite(w.grad).all()
  opt.step();m.eval()
  with torch.no_grad():out=m(x,a);vl=float(objective(out,p,va));tl=float(objective(out,p,tr))
  history.append([tl,vl])
  if vl<best:best=vl;state=copy.deepcopy(m.state_dict())
 assert min(v[0] for v in history)<history[0][0];m.load_state_dict(state);m.eval()
 with torch.no_grad():out=m(x,a).numpy();q=ordered_quantiles(torch.from_numpy(out)).numpy()
 assert np.all(q[:,0]<=q[:,1]) and np.all(q[:,1]<=q[:,2]) and np.isfinite(out).all()
 # MC dropout uncertainty uses an explicit repeatable seed and freezes attention/GRU.
 torch.manual_seed(seed+1);m.drop.train();draw=[]
 with torch.no_grad():
  for j in range(24):draw.append(m(x,a).numpy())
 m.eval();draw=np.stack(draw);uncertainty=draw.std(0);assert np.isfinite(uncertainty).all() and np.all(uncertainty>=0)
 # Integrated gradients use graph-coupled inputs; check gradients without claiming
 # numerical completeness at a kink or through LayerNorm with only 12 quadrature steps.
 integrated=torch.zeros_like(x)
 for alpha in np.linspace(1/12,1,12):
  z=(x*float(alpha)).detach().requires_grad_(True);score=m(z,a)[52:,0].sum();grad=torch.autograd.grad(score,z)[0];assert torch.isfinite(grad).all();integrated+=grad/12
 attribution=(integrated*x).detach().numpy();assert np.isfinite(attribution).all()
 # Eight-step PGD evaluates bounded feature perturbation; no robustness success assumed.
 attack=x.clone();eps=.08
 for j in range(8):
  attack=attack.detach().requires_grad_(True);l=objective(m(attack,a),p,np.arange(52,64));g=torch.autograd.grad(l,attack)[0];delta=torch.clamp(attack.detach()+.02*g.sign()-x,-eps,eps);delta[:52]=0;attack=x+delta
 assert torch.all(torch.abs(attack-x)<=eps+1e-6) and torch.equal(attack[:52],x[:52])
 with torch.no_grad():adversarial=m(attack,a).numpy()
 return m,out,dict(history=history,hidden=h,masked_entries=int(mask.sum()),uncertainty_test_mean=float(uncertainty[52:].mean()),uncertainty_max=float(uncertainty.max()),attribution_l1=float(np.abs(attribution).sum()),adversarial_prediction_shift=float(np.mean(np.abs(adversarial[52:]-out[52:]))),quantile_ordered=True,dropout_draws=24,attribution_steps=12,attack_steps=8,attack_bound=eps),masked
def main():
 start=time.time();d=tables();c=connect();records=[];(ROOT/'compound-models').mkdir(exist_ok=True)
 with c.cursor() as q:
  q.execute('CREATE TABLE IF NOT EXISTS ml_hybrid_models(case_id INT PRIMARY KEY,model_data LONGBLOB,model_hash VARCHAR(64))');q.execute('CREATE TABLE IF NOT EXISTS ml_hybrid_predictions(case_id INT,eid INT,payload TEXT)')
  for n in ['ml_hybrid_models','ml_hybrid_predictions']:q.execute(f'SELECT COUNT(*) FROM {n}');assert q.fetchone()[0]==0
 for k in range(100):
  i=(k*37)%1000;t=time.perf_counter();ref=native(d,i);facts=read(c,query(i));compare(ref,facts);p=prepared(facts,i,d['edges']);rp=prepared(ref,i,d['edges']);m,out,stats,masked=fit_hybrid(p,i);oracle,expected,expected_stats,expected_masked=fit_hybrid(rp,i)
  np.testing.assert_array_equal(out,expected);assert stats==expected_stats;np.testing.assert_array_equal(masked,expected_masked)
  b=io.BytesIO();torch.save(m.state_dict(),b);blob=b.getvalue();sha=hashlib.sha256(blob).hexdigest();rows=[(k,int(p['ids'][j]),json.dumps(out[j].tolist())) for j in range(52,64)];commit=k%2==0
  with c.cursor() as q:
   q.execute('BEGIN');q.execute('INSERT INTO ml_hybrid_models VALUES(%s,%s,%s)',(k,blob,sha));q.executemany('INSERT INTO ml_hybrid_predictions VALUES(%s,%s,%s)',rows);q.execute('SELECT model_data,model_hash FROM ml_hybrid_models WHERE case_id=%s',(k,));stored,hs=q.fetchone();assert stored==blob and hs==sha
   reload=Hybrid(stats['hidden']);reload.load_state_dict(torch.load(io.BytesIO(stored),weights_only=True));reload.eval()
   with torch.no_grad():pred=reload(torch.from_numpy(masked),torch.from_numpy(p['adj'])).numpy()
   np.testing.assert_array_equal(pred,out);q.execute('SELECT eid,payload FROM ml_hybrid_predictions WHERE case_id=%s ORDER BY eid',(k,));got=q.fetchall();assert [r[0] for r in got]==p['ids'][52:].tolist();np.testing.assert_array_equal(np.array([json.loads(r[1]) for r in got],np.float32),out[52:]);q.execute('COMMIT' if commit else 'ROLLBACK')
   view=connect()
   with view.cursor() as v:
    v.execute('SELECT COUNT(*) FROM ml_hybrid_models WHERE case_id=%s',(k,));assert v.fetchone()[0]==int(commit)
    v.execute('SELECT COUNT(*) FROM ml_hybrid_predictions WHERE case_id=%s',(k,));assert v.fetchone()[0]==12*int(commit)
   view.close();q.execute('DELETE FROM ml_hybrid_predictions WHERE case_id=%s',(k,));q.execute('DELETE FROM ml_hybrid_models WHERE case_id=%s',(k,))
  (ROOT/'compound-models'/f'{k:03d}.pt').write_bytes(blob);r=dict(case_id=k,config_i=i,status='pass',model_bytes=len(blob),model_sha256=sha,stats=stats,seconds=time.perf_counter()-t,transaction='commit' if commit else 'rollback',train_entities=40,validation_entities=12,test_entities=12,layers='3 CNN + 2 GRU + 3 attention blocks + 3 GCN + 2 head linear',tasks=['future_regression','future_risk','masked_reconstruction','ordered_quantiles'],predictions=out[52:].tolist());records.append(r)
  with (ROOT/'compound-cases.jsonl').open('a') as f:f.write(json.dumps(r,separators=(',',':'))+'\n')
  if (k+1)%10==0:print(json.dumps(dict(passed=k+1,seconds=time.time()-start)),flush=True)
 c.close();(ROOT/'compound-summary.json').write_text(json.dumps(dict(passed=100,failed=0,seconds=time.time()-start),indent=2))
if __name__=='__main__':main()

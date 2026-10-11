"""Post-training: replay ALL 20k models against fresh MO features, with no labels."""
import concurrent.futures,hashlib,json,time
import numpy as np
from data import ROOT,connect,read,query,tables,native,compare
from models import FEATURES,reload,predict,numpy_forward
from serving import transform
def worker(w,configs,lookup,registry):
 c=connect();edges=read(c,'SELECT * FROM edges ORDER BY src,dst');d=tables();compare(d['edges'].astype(float).sort_values(['src','dst']).reset_index(drop=True),edges,1e-12);results=[]
 for i in configs:
  full=read(c,query(i));compare(native(d,i),full);raw=full[['eid','split_id','anchor','day']+FEATURES];p=transform(raw,edges,i,registry[str(i)])
  for m in range(20):
   cid=m*1000+i;r=lookup[cid];feature_hash=hashlib.sha256(p['x'].astype('<f4').tobytes()).hexdigest();assert feature_hash==r['feature_sha256'];blob=(ROOT/'models'/f'{cid:05d}.pt').read_bytes();assert hashlib.sha256(blob).hexdigest()==r['model_sha256'];net=reload(blob,m,i);out=predict(net,p);assert hashlib.sha256(out.astype('<f4').tobytes()).hexdigest()==r['prediction_sha256'];np.testing.assert_array_equal(out[52:],np.array(r['test_predictions'],np.float32));ni=numpy_forward(net,p);np.testing.assert_allclose(ni,out,rtol=3e-5,atol=3e-5);result=dict(case_id=cid,status='pass',fresh_mo_features=True,preprocessing_refitted=False,labels_passed_to_inference=False,prediction_bit_exact=True,numpy_max_abs_error=float(np.max(np.abs(out-ni))));results.append(result)
  if len(results)%1000==0:print(json.dumps(dict(worker=w,replayed=len(results))),flush=True)
 c.close();return results
def main():
 start=time.time();lookup={}
 for f in ROOT.glob('main-worker-*.jsonl'):
  for l in f.open():
   r=json.loads(l);assert r['status']=='pass';lookup[r['case_id']]={k:r[k] for k in ['feature_sha256','prediction_sha256','test_predictions']};lookup[r['case_id']]['model_sha256']=r['model']['sha256']
 assert len(lookup)==20000;registry=json.loads((ROOT/'preprocessing.json').read_text())
 with concurrent.futures.ProcessPoolExecutor(max_workers=2) as pool:
  fs=[pool.submit(worker,w,[i for i in range(1000) if (i//4)%2==w],lookup,registry) for w in range(2)];results=[r for f in fs for r in f.result()]
 results.sort(key=lambda r:r['case_id']);assert [r['case_id'] for r in results]==list(range(20000));(ROOT/'serving-checks.jsonl').write_text(''.join(json.dumps(r,separators=(',',':'))+'\n' for r in results));summary=dict(replayed=20000,passed=20000,failed=0,seconds=time.time()-start,fresh_mo_feature_queries=1000,model_binary_hashes=20000,bit_exact_predictions=20000,ground_truth_columns_supplied=False,preprocessing_refitted=False,scope='Post-training phase on the same canonical IDs, not 20000 additional distinct training cases. Preprocessing registry loaded unchanged, no labels enter inference.');(ROOT/'serving-summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary))
if __name__=='__main__':main()

"""Replay a canonical case from its exact retained model, without retraining."""
import argparse,hashlib,json
import numpy as np,pandas as pd
from data import ROOT,connect,tables,native,query,read,compare
from models import prepared,reload,predict,numpy_forward,evaluate
def main():
 ap=argparse.ArgumentParser();ap.add_argument('case_id',type=int);ap.add_argument('--offline',action='store_true');ap.add_argument('--retrain',action='store_true');args=ap.parse_args();cid=args.case_id;assert 0<=cid<20000
 record=None
 for l in (ROOT/'cases.jsonl').open():
  r=json.loads(l)
  if r['case_id']==cid:record=r;break
 assert record is not None;mission,i=divmod(cid,1000);d=tables();reference=native(d,i)
 if args.offline:
  d={n:pd.read_csv(ROOT/'inputs'/f'{n}.csv.gz',float_precision='round_trip') for n in d};facts=native(d,i);compare(reference,facts,1e-12);edges=d['edges']
 else:
  c=connect();facts=read(c,query(i));edges=read(c,'SELECT * FROM edges').sort_values(['src','dst']).reset_index(drop=True);compare(d['edges'].astype(float).sort_values(['src','dst']).reset_index(drop=True),edges,1e-12);c.close();compare(reference,facts)
 p=prepared(facts,i,edges);assert hashlib.sha256(p['x'].astype('<f4').tobytes()).hexdigest()==record['feature_sha256']
 for name,k in [('mu','mu'),('sd','sd'),('target_mu','ym'),('target_sd','ys')]:np.testing.assert_array_equal(np.array(record['preprocessing'][name]),p[k])
 blob=(ROOT/'models'/f'{cid:05d}.pt').read_bytes();assert hashlib.sha256(blob).hexdigest()==record['model']['sha256'];net=reload(blob,mission,i);out=predict(net,p);np.testing.assert_array_equal(out[52:],np.array(record['test_predictions'],np.float32));assert hashlib.sha256(out.astype('<f4').tobytes()).hexdigest()==record['prediction_sha256'];np.testing.assert_allclose(numpy_forward(net,p),out,rtol=3e-5,atol=3e-5);assert evaluate(out,p,net.task)==record['metrics']
 if args.retrain:
  from models import fit
  m,pred,metrics=fit(p,mission,i);np.testing.assert_array_equal(pred,out);assert metrics==record['training']
 result=dict(case_id=cid,status='pass',offline=args.offline,retrained=args.retrain,model_hash_exact=True,prediction_exact=True,independent_numpy=True,metrics=record['metrics']);print(json.dumps(result));
 with (ROOT/'replay-results.jsonl').open('a') as f:f.write(json.dumps(result)+'\n')
if __name__=='__main__':main()

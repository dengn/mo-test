"""Ground-truth-free inference from saved preprocessing and exact model binaries."""
import argparse,hashlib,json
import numpy as np,pandas as pd
from data import ROOT,tables,native,read,query,connect
from models import FEATURES,prepared,params,reload,predict,numpy_forward
def export_preprocessing():
 d=tables();out={}
 for i in range(1000):
  p=prepared(native(d,i),i,d['edges']);out[str(i)]={k:p[k].tolist() for k in ['median','mu','sd','ym','ys']}
 (ROOT/'preprocessing.json').write_text(json.dumps(out,separators=(',',':')));print({'preprocessing_configurations_exported':len(out)})
def transform(raw,edges,i,stored):
 # Reject accidentally passing outcome columns to the serving transformation.
 allowed=['eid','split_id','anchor','day']+FEATURES
 assert set(raw.columns)==set(allowed),'serving receives feature columns only'
 cfg=params(i);L=cfg['length'];x=raw[FEATURES].to_numpy(np.float32).reshape(64,L,-1).astype(float);rr=np.random.default_rng(910000+i);x[rr.random(x.shape)<cfg['missing']*.015]=np.nan;x[:,:,:4]+=rr.normal(0,cfg['noise'],(64,L,4));x=np.where(np.isnan(x),np.array(stored['median']),x);z=np.clip((x-np.array(stored['mu']))/np.array(stored['sd']),-8,8).astype(np.float32)
 ids=raw.eid.to_numpy(np.int64).reshape(64,L)[:,0];sp=raw.split_id.to_numpy(np.int64).reshape(64,L)[:,0];index={int(v):j for j,v in enumerate(ids)};adj=np.eye(64,dtype=np.float32)
 for src,dst,w in edges.itertuples(index=False,name=None):
  if int(src) in index and int(dst) in index and sp[index[int(src)]]==sp[index[int(dst)]]:adj[index[int(src)],index[int(dst)]]+=w
 adj/=adj.sum(1,keepdims=True)
 return dict(x=np.ascontiguousarray(z),adj=np.ascontiguousarray(adj))
def main():
 ap=argparse.ArgumentParser();ap.add_argument('case_id',nargs='?',type=int);ap.add_argument('--offline',action='store_true');ap.add_argument('--export',action='store_true');args=ap.parse_args()
 if args.export:export_preprocessing();return
 cid=args.case_id;assert cid is not None and 0<=cid<20000;mission,i=divmod(cid,1000);r=next(json.loads(l) for l in (ROOT/'cases.jsonl').open() if json.loads(l)['case_id']==cid);stored=json.loads((ROOT/'preprocessing.json').read_text())[str(i)];d=tables()
 if args.offline:
  d={n:pd.read_csv(ROOT/'inputs'/f'{n}.csv.gz',float_precision='round_trip') for n in d};full=native(d,i);edges=d['edges']
 else:
  c=connect();full=read(c,query(i));edges=read(c,'SELECT * FROM edges');c.close()
 raw=full[['eid','split_id','anchor','day']+FEATURES];p=transform(raw,edges,i,stored);assert hashlib.sha256(p['x'].astype('<f4').tobytes()).hexdigest()==r['feature_sha256'];blob=(ROOT/'models'/f'{cid:05d}.pt').read_bytes();assert hashlib.sha256(blob).hexdigest()==r['model']['sha256'];m=reload(blob,mission,i);out=predict(m,p);assert hashlib.sha256(out.astype('<f4').tobytes()).hexdigest()==r['prediction_sha256'];np.testing.assert_array_equal(out[52:],np.array(r['test_predictions'],np.float32));np.testing.assert_allclose(numpy_forward(m,p),out,rtol=3e-5,atol=3e-5)
 result=dict(case_id=cid,status='pass',offline=args.offline,ground_truth_supplied_to_inference=False,preprocessing_refitted=False,predictions_exact=True);print(json.dumps(result))
 with (ROOT/'serving-replay-results.jsonl').open('a') as f:f.write(json.dumps(result)+'\n')
if __name__=='__main__':main()

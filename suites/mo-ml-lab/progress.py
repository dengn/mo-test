import collections,json,shutil,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent
c=collections.Counter();arch=collections.Counter();byworker={};quality=collections.Counter();sizes=[];errs=[];nperr=0.;best0=0;epochs=0;sqlrows=0
for f in ROOT.glob('main-worker-*.jsonl'):
 n=0
 for l in f.open():
  try:r=json.loads(l)
  except ValueError:continue
  n+=1;c[r['status']]+=1
  if r['status']!='pass':
   if len(errs)<3:errs.append(r)
   continue
  arch[r['mission']['architecture']]+=1;sizes.append(r['model']['bytes']);nperr=max(nperr,r['independent_numpy_max_abs_error']);best0+=r['training']['best_epoch']==0;epochs+=r['training']['epochs'];sqlrows+=r['fact_rows']
  m=r['metrics']
  if 'baseline_rmse' in m:quality['forecast_total']+=1;quality['forecast_beats_baseline']+=m['rmse']<m['baseline_rmse']
 byworker[f.stem]=n
start=json.loads((ROOT/'main-start.json').read_text())['start_utc_epoch'];health=json.loads((ROOT/'main-health.jsonl').read_text().splitlines()[-1]);disk=shutil.disk_usage(ROOT)
print(json.dumps(dict(status=dict(c),workers=byworker,architectures=dict(arch),elapsed=time.time()-start,model_bytes_min=min(sizes) if sizes else 0,model_bytes_max=max(sizes) if sizes else 0,numpy_error_max=nperr,validation_selected_initial_checkpoint=best0,epochs=epochs,feature_rows=sqlrows,quality=dict(quality),latest_health=health,disk_free_bytes=disk.free,errors=errs),ensure_ascii=False))

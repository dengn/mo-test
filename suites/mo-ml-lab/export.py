"""Lossless input export and reproducible scenario catalog."""
import hashlib,json,shutil
from data import ROOT,SCHEMAS,SEED,tables,query,params
from models import MISSIONS
def main():
 (ROOT/'inputs').mkdir(exist_ok=True);manifest={}
 for n,f in tables().items():
  path=ROOT/'inputs'/f'{n}.csv.gz';f.to_csv(path,index=False,float_format='%.17g',compression={'method':'gzip','mtime':0});manifest[n]=dict(rows=len(f),columns=list(f),dtypes={k:str(v) for k,v in f.dtypes.items()},ddl=SCHEMAS[n],sha256=hashlib.sha256(path.read_bytes()).hexdigest())
 (ROOT/'input-manifest.json').write_text(json.dumps(dict(seed=SEED,tables=manifest),indent=2));(ROOT/'scenario-catalog.json').write_text(json.dumps(dict(missions=MISSIONS,configurations=[params(i) for i in range(1000)],case_id='mission_id * 1000 + configuration_i',fact_sql_distinct=1000,independent_model_configurations=20000,scope='Each configuration changes entity scope, temporal anchors/horizon/length and interacting network/training/noise/missingness settings. The 20 missions share 1000 fact-query designs; every main case reads MO and trains anew.'),indent=2));(ROOT/'example.sql').write_text(query(443));(ROOT/'jars').mkdir(exist_ok=True);shutil.copy2('/workspace/mo-ds-lab/jars/mysql-connector-j-8.0.33.jar',ROOT/'jars/mysql-connector-j-8.0.33.jar');print({'tables_exported':len(manifest),'rows':sum(v['rows'] for v in manifest.values())})
if __name__=='__main__':main()

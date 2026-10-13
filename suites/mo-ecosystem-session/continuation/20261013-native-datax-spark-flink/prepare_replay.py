"""Prepare a fresh replay workspace. Starts no services; creates no SQL data."""
from pathlib import Path
import os,json,shutil,hashlib,uuid,re
PACKAGE=Path(__file__).parent
root=Path(os.environ['MO_NATIVE_REPLAY_ROOT']).resolve()
assert not root.exists(),'Choose a new workspace; old results are never adopted'
assert os.environ.get('MO_NATIVE_REPLAY_ACCEPT_LIMITS')=='1','Explicitly accept 6GiB used filesystem cap, 2GiB free and 3GiB estimated memory headroom'
ds=os.environ.get('MO_TEST_DATABASE','');assert re.fullmatch(r'mo_ecosystem_native_[a-z0-9]{8,24}',ds),'Set a unique new mo_ecosystem_native_<suffix> database'
assert os.environ.get('MO_PORT')=='16001' and os.environ.get('MYSQL_PORT')=='23306','This frozen Flink source uses localhost23306; use the measured endpoint layout'
for k in ['MO_PASSWORD','MYSQL_PASSWORD','DATAX_HOME','MO_JDBC_JAR','JAVA8_HOME','JAVA17_HOME','FLINK_HOME']:assert k in os.environ,'Missing '+k
root.mkdir(parents=True);D=root/'native-dsf';D.mkdir();W=root/'windowed';W.mkdir();(root/'results').mkdir()
man=[]
for folder,target in [('windowed',W),('native-dsf',D)]:
 for p in (PACKAGE/'frozen-source'/folder).iterdir():
  if p.suffix not in ['.py','.java']:continue
  source=p.read_text();s=source
  if p.name=='native_batch.py':
   s=s.replace("DATAX=Path('/workspace/work/etl-expanded/datax')","DATAX=Path(os.environ['DATAX_HOME'])")
   s=s.replace("JDBC=SEATUNNEL/'lib/mysql-jdbc.jar'","JDBC=Path(os.environ['MO_JDBC_JAR'])")
  if p.name=='flink_cdc.py':
   for old,envkey in [('/workspace/work/etl-expanded/jars/mysql-cdc-3.6.0-1.20.jar','FLINK_MYSQL_CDC_JAR'),('/workspace/work/path-verification/jars/flink-jdbc.jar','FLINK_JDBC_JAR'),('/workspace/work/path-verification/jars/mysql-jdbc.jar','MO_JDBC_JAR')]:
    assert envkey in os.environ;assert Path(os.environ[envkey]).is_file();s=s.replace(repr(old),'os.environ['+repr(envkey)+']')
  if p.name=='recycle_profile.py':s=s.replace("DS=='mo_ecosystem_heavy_20261012'","DS.startswith('mo_ecosystem_native_')")
  if p.name=='guard_6g.py':s=s.replace("os.environ['MO_TEST_DATABASE']=='mo_ecosystem_heavy_20261012'","os.environ['MO_TEST_DATABASE'].startswith('mo_ecosystem_native_')")
  s=s.replace('archive_profile(tool,name,apply=True)',"archive_profile(tool,name,apply=os.environ.get('MO_NATIVE_REPLAY_REUSE')=='1')")
  s=s.replace('archive_profile(route,name,apply=True)',"archive_profile(route,name,apply=os.environ.get('MO_NATIVE_REPLAY_REUSE')=='1')")
  s=s.replace("archive_profile('flinkcdc5','native',apply=True)","archive_profile('flinkcdc5','native',apply=os.environ.get('MO_NATIVE_REPLAY_REUSE')=='1')")
  out=target/p.name;out.write_text(s)
  if p.suffix=='.py':compile(s,str(out),'exec')
  man.append({'path':str(out.relative_to(root)),'frozen_sha256':hashlib.sha256(source.encode()).hexdigest(),'replay_sha256':hashlib.sha256(s.encode()).hexdigest()})
inventory={k:{'home':str(Path(os.environ[v]).resolve())} for k,v in [('jre8','JAVA8_HOME'),('jre17','JAVA17_HOME'),('flink','FLINK_HOME')]}
for x in ['jre8','jre17']:assert (Path(inventory[x]['home'])/'bin/java').is_file()
assert (Path(inventory['flink']['home'])/'lib/flink-dist-1.20.2.jar').is_file(),'Use a separate complete Flink1.20.2 installation'
(D/'java-runtime-inventory.json').write_text(json.dumps(inventory,indent=2))
(D/'capacity-approval-6g.json').write_text(json.dumps({'approved':True,'max_used_bytes':6*1024**3,'scope':'fresh replay workspace; explicit MO_NATIVE_REPLAY_ACCEPT_LIMITS opt-in; no original session approval inherited'},indent=2))
profiles=['int64','uint64','decimal38_18','decimal65_30','varchar_utf8','varbinary','datetime6','time6']
tables=[{'route':r,'profile':n,'table':p+'_'+r+'_'+n} for r in ['dataxscan','sparkscan'] for n in profiles for p in ['t','s','e']]
tables += [{'route':'dataxstage','profile':n,'table':p+'_dataxstage_'+n} for n in ['datetime6','time6'] for p in ['t','s','e']]
tables += [{'route':'flinkcdc5','profile':'native','table':p+'_flinkcdc5_native'} for p in ['t','s','e']]
(root/'table-reuse-review-plan.json').write_text(json.dumps({'tables':tables},indent=2))
(root/'table-reuse-approval.json').write_text(json.dumps({'approved':os.environ.get('MO_NATIVE_REPLAY_REUSE')=='1','scope':'only newly registered empty tables in this fresh unique replay database; full archive plus independent reread required'}))
(root/'replay-source-manifest.json').write_text(json.dumps(man,indent=2))
print('Prepared fresh runner files. Services and SQL databases have NOT been created.')
print('Set MO_CASE_OUTPUT='+str(root/'results')+' and MO_CASE_MIN_FREE_MIB=2048 before replay.')
print('Use bootstrap.py to create only a fresh synthetic database, then run native-dsf/actual_batch.py dataxscan; sparkscan; datax_temporal_stage.py; flink_cdc.py in that order.')

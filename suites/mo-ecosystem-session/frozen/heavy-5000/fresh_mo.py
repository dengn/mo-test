from runtime import *
import argparse,re,uuid
P=argparse.ArgumentParser();P.add_argument('--tag',required=True);a=P.parse_args();assert re.fullmatch('[a-z0-9-]+',a.tag)
pidpath=B/'mo.pid'
if pidpath.exists():
 pid=int(pidpath.read_text());proc=Path('/proc',str(pid))
 if proc.exists() and proc.joinpath('cmdline').read_bytes():
  assert b'/workspace/matrixone/mo-service' in proc.joinpath('cmdline').read_bytes();os.kill(pid,signal.SIGTERM)
  for _ in range(100):
   if not proc.exists() or proc.joinpath('stat').read_text().split()[2]=='Z':break
   time.sleep(.2)
  else:raise RuntimeError('MO did not stop')
identity='heavy5000-'+a.tag+'-'+uuid.uuid4().hex[:10];C=B/identity/'config';data=B/identity/'data';assert not C.parent.exists();C.mkdir(parents=True);assert not data.exists()
old=B.parent/'pressure-5/mo-config';prior='/workspace/work/path-verification/runtime/mo-data'
for src in old.glob('*.toml'):
 s=src.read_text().replace(prior,str(data)).replace(str(old),str(C)).replace('bucket = "mo-test"','bucket = "'+identity+'"');(C/src.name).write_text(s)
configs='\n'.join(p.read_text() for p in C.glob('*.toml'));buckets=set(re.findall(r'bucket\s*=\s*"([^"]+)"',configs));assert buckets=={identity},buckets
sys.path.append('/workspace/toolchains/python/lib/python3.12/site-packages');import boto3
S=boto3.client('s3',endpoint_url='http://127.0.0.1:9000',aws_access_key_id='minio',aws_secret_access_key='minio123',region_name='us-east-1')
try:S.head_bucket(Bucket=identity)
except Exception as e:
 if e.response['ResponseMetadata']['HTTPStatusCode']!=404:raise
else:raise RuntimeError('Bucket already exists; refuses to overwrite any existing content')
S.create_bucket(Bucket=identity)
cmd=['/workspace/matrixone/mo-service','-launch',str(C/'launch.toml')];p=subprocess.Popen(cmd,cwd='/workspace/matrixone',stdout=(B/'mo-fresh.log').open('ab'),stderr=subprocess.STDOUT,start_new_session=True);pidpath.write_text(str(p.pid));poll(lambda:sql('SELECT 1',database='mo_catalog'),100);sql('CREATE DATABASE IF NOT EXISTS heavy5000',database=None)
dump(B/('fresh-mo-'+a.tag+'.json'),{'tag':a.tag,'pid':p.pid,'config_dir':str(C),'data_dir':str(data),'s3_bucket':identity,'ownership':'New nonexistent directory andbucketverified beforecreation; noexistingdataremoved','scope':'Fresh bounded runtime; priornamespaceandcaseevidence preserved; resetsnotlongsoakproof','UTC':datetime.datetime.now(datetime.timezone.utc).isoformat()});print('FRESH',a.tag,p.pid,identity,flush=True)

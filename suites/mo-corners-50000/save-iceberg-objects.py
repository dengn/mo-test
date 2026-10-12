import os,json,hashlib
from pathlib import Path
import boto3
os.environ.pop('AWS_PROFILE',None);os.environ.pop('AWS_DEFAULT_PROFILE',None)
P=Path('/workspace/mo-corners-50000/iceberg-objects');P.mkdir(exist_ok=True)
s=boto3.client('s3',endpoint_url='http://127.0.0.1:9000',aws_access_key_id='minio',aws_secret_access_key='minio123',region_name='us-east-1');rows=[]
for page in s.get_paginator('list_objects_v2').paginate(Bucket='mo-iceberg'):
 for o in page.get('Contents',[]):
  key=o['Key'];p=(P/key).resolve()
  if not p.is_relative_to(P.resolve()):raise RuntimeError('Unsafe object path')
  data=s.get_object(Bucket='mo-iceberg',Key=key)['Body'].read();p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data);rows.append({'key':key,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
(P/'object-manifest.json').write_text(json.dumps(rows,indent=2));print('Saved',len(rows),'real Iceberg/Avro/Parquet objects, bytes',sum(x['bytes'] for x in rows))

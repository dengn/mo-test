"""Standalone connection and JSON helpers for the capability study."""
import decimal,os
import numpy as np,pandas as pd,pymysql
def connect():
 return pymysql.connect(host=os.getenv('MO_HOST','127.0.0.1'),port=int(os.getenv('MO_PORT','6001')),user=os.getenv('MO_USER','root'),password=os.getenv('MO_PASSWORD','111'),database=os.getenv('MO_TS_DATABASE','ds_timeseries_20261011'),autocommit=True,connect_timeout=10,read_timeout=60,write_timeout=60)
def read(c,sql):
 with c.cursor() as q:q.execute(sql);return pd.DataFrame(q.fetchall(),columns=[d[0] for d in q.description])
def plain(x):
 if isinstance(x,dict):return {str(k):plain(v) for k,v in x.items()}
 if isinstance(x,(list,tuple,np.ndarray)):return [plain(v) for v in x]
 if isinstance(x,np.generic):x=x.item()
 if isinstance(x,decimal.Decimal):return float(x)
 if isinstance(x,float) and not np.isfinite(x):return None if np.isnan(x) else str(x)
 return x

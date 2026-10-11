import hashlib,json
import numpy as np,pandas as pd

def equal(a,b):
    if isinstance(a,dict):return isinstance(b,dict) and a.keys()==b.keys() and all(equal(a[k],b[k]) for k in a)
    if isinstance(a,(list,tuple,np.ndarray)):return isinstance(b,(list,tuple,np.ndarray)) and len(a)==len(b) and all(equal(x,y) for x,y in zip(a,b))
    if a is None or b is None:return a is b
    if isinstance(a,(str,bool)):return a==b
    return bool(np.isclose(float(a),float(b),rtol=1e-6,atol=1e-6,equal_nan=True))

def compare(e,a):
    assert list(e)==list(a),(list(e),list(a))
    assert e.shape==a.shape,(e.shape,a.shape)
    x=e.to_numpy(float);y=a.to_numpy(float)
    diff=~np.isclose(x,y,rtol=1e-7,atol=1e-7,equal_nan=True)
    if diff.any():
        rows,cols=np.where(diff);raise AssertionError([(int(r),e.columns[int(c)],x[r,c],y[r,c]) for r,c in zip(rows[:12],cols[:12])])
    for k in ['cid','pid','region','tier','category','defaulted','active','clean_history','unpaid_order','confirmed_journey','uncovered_stockout','premium','on_hand','lead_days','supplier','country','calendar_days']:
        if k in e:assert np.array_equal(e[k].to_numpy(),a[k].to_numpy()),k

def receipt(df):
    return dict(rows=len(df),columns=list(df),sha256_float64=hashlib.sha256(df.to_numpy('<f8').tobytes()).hexdigest(),sample=df.head(2).to_numpy(float).tolist()+df.tail(2).to_numpy(float).tolist())

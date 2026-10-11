import hashlib,json,time
import numpy as np,pandas as pd
from data import ROOT,tables,connect

def snapshot(tag='initial'):
    expected=tables();actual={};c=connect();results={}
    for name,e in expected.items():
        with c.cursor() as q:q.execute('SELECT * FROM '+name);a=pd.DataFrame(q.fetchall(),columns=[d[0] for d in q.description])
        for col,dt in e.dtypes.items():
            if 'datetime' in str(dt):a[col]=pd.to_datetime(a[col])
            else:a[col]=a[col].astype(dt)
        # Tables without a primary key may be returned in a different physical order.
        keys=list(e.columns);ee=e.sort_values(keys,na_position='last').reset_index(drop=True);aa=a.sort_values(keys,na_position='last').reset_index(drop=True)
        assert ee.shape==aa.shape,(name,ee.shape,aa.shape)
        for col,dt in ee.dtypes.items():
            if 'float' in str(dt):assert np.allclose(ee[col],aa[col],rtol=1e-12,atol=1e-12,equal_nan=True),(name,col)
            else:assert ee[col].equals(aa[col]),(name,col)
        actual[name]=a;results[name]={'rows':len(a),'full_content':'pass'}
    c.close();r={'time':time.time(),'tables':results,'rows':sum(len(x) for x in actual.values())}
    (ROOT/f'source-audit-{tag}.json').write_text(json.dumps(r,indent=2));return actual

if __name__=='__main__':snapshot('final')

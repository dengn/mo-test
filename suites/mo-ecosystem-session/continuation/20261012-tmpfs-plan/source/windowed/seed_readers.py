"""Recreate the native PETL typed source rows used by the read-only heavy cases."""
from heavy import *
if __name__=='__main__':
 verify_ownership();receipts=[]
 for pi,p in enumerate(PROFILES):
  for port in [6001,13306]:
   create('petl',p,port)
   r=run_case('petl',p,'append',0,port,100000+caseid(pi,0,0))
   receipts.append(r)
   if r['status']!='passed':
    dump(B/'seed-readers.json',receipts)
    raise RuntimeError('Native PETL fixture failed: '+r['id'])
 dump(B/'seed-readers.json',receipts)
 print('Validated 50 source fixtures / 1600 physical rows; these are setup, not 5000 new cases')

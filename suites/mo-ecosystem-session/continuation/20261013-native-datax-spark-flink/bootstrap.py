"""Create only a fresh synthetic replay database, refusing every existing name."""
import os,sys
from pathlib import Path
root=Path(os.environ['MO_NATIVE_REPLAY_ROOT']);sys.path.insert(0,str(root/'windowed'))
import runtime as rt
assert rt.DS.startswith('mo_ecosystem_native_')
sys.path.insert(0,str(root/'native-dsf'));import guard_6g;guard_6g.install();rt.guard()
# Check both endpoints before creating either database; do not adopt old data.
for role in [6001,13306]:
 assert rt.sql('SHOW DATABASES LIKE %s',(rt.DS,),port=role,database=None)==(),'Database already exists; choose another unique suffix'
rt.initialize();print('Created two fresh synthetic replay databases and ownership markers')

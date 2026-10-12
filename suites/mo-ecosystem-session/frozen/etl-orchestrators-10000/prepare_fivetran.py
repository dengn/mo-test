import pathlib,sys,json,ast
B=pathlib.Path(__file__).resolve().parent
root=ast.parse((B/'worker.py').read_text());names={'decode','normalize','canon','sha'};code='import json,decimal,datetime,hashlib\ndecimal.getcontext().prec=80\n'+ '\n'.join(ast.unparse(n) for n in root.body if isinstance(n,ast.FunctionDef) and n.name in names)+'\n';(B/'codec.py').write_text(code)
sys.path.insert(0,str(B.parent/'etl-10000'));import matrix as m
for port in [6001,13306]:
 for p in m.PROFILES:
  t='fivetran_delta_'+p['name'];m.sql('CREATE TABLE IF NOT EXISTS '+t+'(case_id BIGINT,id BIGINT,v '+p['ddl']+',label VARCHAR(256),rev BIGINT,PRIMARY KEY(case_id,id))',port=port,database='orchestrator10000');m.sql('DELETE FROM '+t,port=port,database='orchestrator10000');m.sql('INSERT INTO '+t+' SELECT * FROM dbt_delta_'+p['name'],port=port,database='orchestrator10000')
print('Prepared Fivetran typed sources and native deltas')

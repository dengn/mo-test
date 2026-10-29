import sys,pathlib,json
B=pathlib.Path(__file__).resolve().parent;sys.path.insert(0,str(B.parent/'etl-10000'));import matrix as m
cs=json.loads((B/'fixtures.json').read_text());project=B/'dbt-project';(project/'models').mkdir(parents=True,exist_ok=True);(project/'tests').mkdir(exist_ok=True)
(project/'dbt_project.yml').write_text("name: matrixone_ecosystem\nversion: '1.0'\nconfig-version: 2\nprofile: ecosystem\nmodel-paths: ['models']\ntest-paths: ['tests']\nmodels:\n  matrixone_ecosystem:\n    +materialized: table\n")
(project/'profiles.yml').write_text("ecosystem:\n  target: mo\n  outputs:\n    mo:\n      type: mysql\n      server: 127.0.0.1\n      port: 6001\n      username: root\n      password: '111'\n      schema: orchestrator10000\n      charset: utf8mb4\n      collation: utf8mb4_bin\n      threads: 2\n    mysql:\n      type: mysql\n      server: 127.0.0.1\n      port: 13306\n      username: root\n      password: types-local\n      schema: orchestrator10000\n      charset: utf8mb4\n      collation: utf8mb4_bin\n      threads: 2\n")
for pi,p in enumerate(m.PROFILES):
 lo=pi*50+1;transformlo=lo+20;mergelo=lo+30;deadlo=lo+40;table='dbt_'+p['name'];delta='dbt_delta_'+p['name']
 for port in [6001,13306]:
  m.sql('CREATE TABLE IF NOT EXISTS '+delta+'(case_id BIGINT,id BIGINT,v '+p['ddl']+',label VARCHAR(256),rev BIGINT,PRIMARY KEY(case_id,id))',port=port,database='orchestrator10000')
  changes=[]
  for c in cs:
   if c['profile']==p['name'] and c['scenario']=='staging_merge':
    extra=m.values(p,c['seed']+11);cid=c['logical_case_id'];rows=m.base_rows(cid,p,c['seed']);changes.extend([[cid,1,extra[0],'更新😀'+str(c['seed']),1],[cid,3,extra[1],'更新😀'+str(c['seed']),1],[cid,len(rows),extra[2],'新增😀'+str(c['seed']),1]])
  with m.db(port,'orchestrator10000',False) as d,d.cursor() as cur:cur.execute('DELETE FROM '+delta);cur.executemany('INSERT INTO '+delta+' VALUES(%s,%s,%s,%s,%s)',changes);d.commit()
 q=f'''SELECT b.case_id,b.id,
CASE WHEN incoming.id IS NOT NULL THEN incoming.v ELSE b.v END AS v,
CASE WHEN b.case_id BETWEEN {transformlo} AND {transformlo+9} THEN CONCAT(b.label,'→ETL',CAST(b.case_id-{transformlo} AS CHAR)) WHEN incoming.id IS NOT NULL THEN incoming.label ELSE b.label END AS label,
CASE WHEN b.case_id BETWEEN {transformlo} AND {transformlo+9} THEN b.rev+b.case_id-{transformlo}+1 WHEN incoming.id IS NOT NULL THEN incoming.rev ELSE b.rev END AS rev
FROM `orchestrator10000`.`{table}` AS b LEFT JOIN `orchestrator10000`.`{delta}` AS incoming ON b.case_id=incoming.case_id AND b.id=incoming.id
WHERE (b.case_id NOT BETWEEN {transformlo} AND {transformlo+9} OR MOD(b.id,2)=MOD(b.case_id-{transformlo},2)) AND (b.case_id NOT BETWEEN {deadlo} AND {deadlo+9} OR (b.id<>1 AND b.id<(SELECT MAX(z.id)-1 FROM `orchestrator10000`.`{table}` AS z WHERE z.case_id=b.case_id)) OR (b.case_id BETWEEN {deadlo} AND {deadlo+9} AND b.id=(SELECT MAX(z.id) FROM `orchestrator10000`.`{table}` AS z WHERE z.case_id=b.case_id)))
UNION ALL SELECT incoming.case_id,incoming.id,incoming.v,incoming.label,incoming.rev FROM `orchestrator10000`.`{delta}` AS incoming LEFT JOIN `orchestrator10000`.`{table}` AS original ON original.case_id=incoming.case_id AND original.id=incoming.id WHERE original.id IS NULL
'''
 # Delete exactly id1 and penultimate id; correlated MAX uses explicit aliases to avoid known issue #29876.
 (project/'models'/('out_'+p['name']+'.sql')).write_text(q)
 (project/'tests'/('key_'+p['name']+'.sql')).write_text("select case_id,id,count(*) AS n from {{ref('out_"+p['name']+"')}} group by case_id,id having count(*)<>1\n")
print('DBT prepared 20 native table models, 20 key tests, 1000 logical oracle cases per endpoint')

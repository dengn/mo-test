"""Post-race and post-restart catalog/table usability checks for issue 29927."""
import json
from pathlib import Path
import pymysql

P=Path(__file__).resolve().parent
TABLES=['race_h','race_i','race_ft','race_ft2']
def connect(db=None,port=6014,timeout=120):
    c=pymysql.connect(host='127.0.0.1',port=port,user='root',password='111',database=db,
        autocommit=True,ssl_disabled=True,connect_timeout=5,read_timeout=timeout)
    for s in ['set experimental_hnsw_index=1','set experimental_fulltext2_index=1',
              'set hnsw_threads_search=1','set probe_limit=128']:
        query(c,s)
    return c
def query(c,s,args=None):
    with c.cursor() as cur:
        cur.execute(s,args)
        return cur.fetchall() if cur.description else []
def verify(db,ledger,phase,outdir,port=6014):
    c=connect(db,port);results=[]
    def check(name,sql,args=None):
        try:
            rows=query(c,sql,args);r={'name':name,'sql':sql,'params':args,'status':'pass','rows':rows}
        except Exception as e:r={'name':name,'sql':sql,'params':args,'status':'error','error':str(e),'code':e.args[0]}
        results.append(r)
        return r
    for table in TABLES:
        check('show_create_'+table,'show create table '+table)
        check('show_index_'+table,'show index from '+table)
        stored=check('source_rows_'+table,'select id,n from '+table)
        if stored['status']=='pass':
            actual=dict(stored['rows']);missing=[];wrong=[]
            for t,i,n in ledger:
                if t==table:
                    if i not in actual:missing.append(i)
                    elif actual[i]!=n:wrong.append([i,n,actual[i]])
            results.append({'name':'acknowledged_writes_'+table,'status':'pass' if not missing and not wrong else 'error',
                            'acknowledged':sum(t==table for t,i,n in ledger),'missing':missing,'wrong':wrong})
            # Keep count/check results, not thousands of duplicate source rows.
            stored['row_count']=len(stored.pop('rows'))
        metadata=check('metadata_'+table,
            'select distinct name,algo,algo_table_type,index_table_name,is_visible from mo_catalog.mo_indexes '
            'where table_id=(select rel_id from mo_catalog.mo_tables where reldatabase=%s and relname=%s) order by name,algo_table_type',
            [db,table])
        if metadata['status']=='pass':
            for internal in sorted({row[3] for row in metadata['rows'] if row[3]}):
                quoted='`'+internal.replace('`','``')+'`'
                check('physical_index_relation_'+table,'select count(*) from '+quoted)
    vector=json.dumps([1.0]*64)
    ident=99010001 if phase=='post_load' else 99010002
    check('fresh_insert_hnsw','insert into race_h values(%s,%s,%s)',[ident,ident*3,vector])
    check('fresh_hnsw_reindex','alter table race_h alter reindex ann hnsw force_sync')
    check('fresh_hnsw_query','select id,l2_distance(v,%s) from race_h where n>=0 order by l2_distance(v,%s) limit 10',[vector,vector])
    check('fresh_ivf_reindex','alter table race_i alter reindex ann ivfflat lists=16')
    check('fresh_ft2_reindex','alter table race_ft2 alter reindex txt fulltext2 merge force_sync')
    check('fresh_secondary_create','create index post_recheck on race_h(n)')
    check('fresh_secondary_drop','drop index post_recheck on race_h')
    check('show_create_after_secondary_ddl','show create table race_h')
    c.close();summary={'database':db,'phase':phase,'checks':results,'errors':[x for x in results if x['status']=='error']}
    Path(outdir).joinpath('verify-'+phase+'.json').write_text(json.dumps(summary,indent=2,default=str)+'\n')
    return summary

from suite import *
c=conn(timeout=180)
def test(name,s,args=None,expect_error=False,expected=None):
    t=time.monotonic()
    try:
        r=sql(c,s,args);ok=not expect_error and (expected is None or r==expected)
        emit('edge',name=name,sql=s[:240],seconds=time.monotonic()-t,accepted=True,rows=len(r),result=r[:12],pass_check=ok if expect_error or expected is not None else None)
        return r
    except Exception as e:
        emit('edge',name=name,sql=s[:240],seconds=time.monotonic()-t,accepted=False,error=str(e),pass_check=expect_error)
sql(c,'drop table if exists edgev')
sql(c,'create table edgev(id bigint primary key,v vecf32(3))')
for name,s,expected,error in [
 ('dimension_short',"insert into edgev values(1,'[1,2]')",None,True),
 ('dimension_long',"insert into edgev values(2,'[1,2,3,4]')",None,True),
 ('nan',"insert into edgev values(3,'[NaN,1,2]')",None,True),
 ('inf',"insert into edgev values(4,'[Inf,1,2]')",None,True),
 ('overflow_literal',"insert into edgev values(5,'[1e100,1,2]')",None,True),
 ('atomic_bad_batch',"insert into edgev values(6,'[1,2,3]'),(7,'[1,2]')",None,True),
 ('invalid_batch_no_partial','select count(*) from edgev',((0,),),False),
 ('float32_distance_overflow',"select l2_distance(cast('[2e19,2e19]' as vecf32(2)),cast('[0,0]' as vecf32(2)))",None,True),
 ('subnormal_cosine_constant',"select cosine_distance(cast('[3e-23,3e-23]' as vecf32(2)),cast('[3e-23,0]' as vecf32(2)))",None,False),
 ('zero_cosine_convention',"select cosine_distance(cast('[0,0,0]' as vecf32(3)),cast('[1,0,0]' as vecf32(3)))",((1.0,),),False),
 ('ordinary_l2',"select l2_distance(cast('[3,4]' as vecf32(2)),cast('[0,0]' as vecf32(2)))",((5.0,),),False),
 ('dimension_65536','create table dimension_bad(v vecf32(65536))',None,True),
 ('dimension_65535','create table if not exists dimension_max(id int primary key,v vecf32(65535))',None,False),
]:test(name,s,expected=expected,expect_error=error)
sql(c,'truncate table dimension_max')
test('max_dimension_insert','insert into dimension_max values(1,%s)',('['+','.join(['0']*65534+['1'])+']',))
test('max_dimension_norm','select l2_norm(v) from dimension_max',expected=((1.0,),))
sql(c,'create table if not exists subnormalv(id bigint primary key,v vecf32(2))');sql(c,'truncate table subnormalv')
sql(c,"insert into subnormalv values(1,'[3e-23,3e-23]'),(2,'[3,4]')")
test('subnormal_cosine_column',"select cosine_distance(v,'[3e-23,0]') from subnormalv order by id",expected=((0.2928932309150696,),(0.4000000059604645,)))
sql(c,"insert into edgev values(10,'[1,0,0]'),(11,'[0,1,0]'),(12,'[0,0,1]'),(13,null)")
test('hnsw_null_build',"create index ann using hnsw on edgev(v) op_type 'vector_cosine_ops'")
test('hnsw_zero_query',"select id from edgev order by cosine_distance(v,'[0,0,0]') limit 2",expect_error=True)
test('hnsw_subnormal_query',"select id from edgev order by cosine_distance(v,'[1e-20,1e-20,1e-20]') limit 2",expect_error=True)
test('hnsw_null_not_returned',"select id from edgev order by cosine_distance(v,'[1,0,0]') limit 10")
test('hnsw_limit_zero',"select id from edgev order by cosine_distance(v,'[1,0,0]') limit 0",expected=())
for parser in ['ngram','gojieba']:
    t='cjk_'+parser;sql(c,f'drop table if exists {t}');sql(c,f'create table {t}(id int primary key,body text)')
    sql(c,f'insert into {t} values(1,%s),(2,%s),(3,%s),(4,%s)',('苹果香蕉','苹果香瓜','苹果香蕉西瓜','红苹果甜'))
    test(parser+'_build',f'create fulltext2 index txt on {t}(body) with parser {parser}')
    for q,ids in [('苹果香蕉*',[1,3]),('+苹果香蕉*',[1,3]),('苹果*',[1,2,3,4])]:
        test(parser+'_'+q,f'select id from {t} where match(body) against(%s in boolean mode) order by id',(q,),expected=tuple((i,) for i in ids))
sql(c,'drop table if exists longft');sql(c,'create table longft(id int primary key,body text)')
test('text_over_65535','insert into longft values(8,%s)',(('repeat ')*20000,),expect_error=True)
rows=[(1,'a'*400),(2,'a'*400+'b'),(3,'hello world'),(4,''),(5,None),(6,'emoji 😀 数据库 矩阵 搜索'),(7,('repeat ')*9000)]
with c.cursor() as q:q.executemany('insert into longft values(%s,%s)',rows)
test('long_fulltext2_build','create fulltext2 index txt on longft(body)')
for q in ['a'*400,'a'*400+'b','','😀','数据库','repeat','+hello -world','"hello world"','+','"','('*32+'hello'+')'*32]:
    test('fulltext_boundary_'+q[:35],'select id from longft where match(body) against(%s in boolean mode) order by id',(q,),expect_error=(q==''))
test('edge_recovery_probe','select 1',expected=((1,),))
c.close()

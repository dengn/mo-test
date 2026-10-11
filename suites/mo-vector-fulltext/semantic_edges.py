from suite import *
c=conn(timeout=180)
sql(c,'create table dimension_h(id bigint primary key,v vecf32(65535))');sql(c,'insert into dimension_h select * from dimension_max')
timed(c,"create index ann using hnsw on dimension_h(v) op_type 'vector_l2_ops'")
v='['+','.join(['0']*65534+['1'])+']';r=sql(c,'select id,l2_distance(v,%s) from dimension_h order by l2_distance(v,%s) limit 10',(v,v))
emit('max_dimension_hnsw',dimension=65535,result=r,pass_check=r==((1,0.0),))
for t,engine in [('utf_ft','fulltext'),('utf_ft2','fulltext2')]:
    sql(c,f'create table {t}(id bigint primary key,body text)')
    sql(c,f'insert into {t} values(1,%s),(2,%s),(3,%s),(4,%s)',('b'*26,'hello '+'b'*26,'a'+'я'*12,'Ⱥ'*8))
    timed(c,f'create {engine} index txt on {t}(body) with parser ngram')
    for q,expected in [('b'*26,{1,2}),('a'+'я'*12,{3}),('Ⱥ'*8,{4})]:
        for mode,pattern in [('',q),(' in boolean mode','"'+q+'"')]:
            r=sql(c,f'select id from {t} where match(body) against(%s{mode})',(pattern,));actual={int(i) for i, in r};emit('unicode_token',table=t,query=pattern,mode=mode,ids=sorted(actual),expected=sorted(expected),pass_check=actual==expected)
# NULL/empty JSON fields and multicolumn token membership.
sql(c,'create table jft(id bigint primary key,a json,b json)')
sql(c,'insert into jft values(1,null,%s),(2,%s,null),(3,%s,%s),(4,%s,%s)',('{"x":"rightonly"}','{"x":"leftonly"}','{"x":"leftboth"}','{"x":"rightboth"}','{"x":null}','{"x":""}'))
timed(c,'create fulltext2 index txt on jft(a,b) with parser json_value')
for query,expected in [('rightonly',{1}),('leftonly',{2}),('+leftboth +rightboth',{3}),('null',set())]:
    r=sql(c,'select id from jft where match(a,b) against(%s in boolean mode)',(query,));actual={int(i) for i, in r};emit('json_fulltext',query=query,ids=sorted(actual),expected=sorted(expected),pass_check=actual==expected)
c.close()

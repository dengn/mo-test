import json,hashlib,random,math,datetime,re,collections
from pathlib import Path
P=Path('/workspace/mo-cases-50000');M=[x for x in json.loads((P/'source-manifest.json').read_text()) if x['status']=='downloaded'];rng=random.Random(20261010)
def source(needle,repo=None):
    matches=[m for m in M if needle.lower() in m['path'].lower() and (repo is None or m['repo'].endswith(repo))]
    if not matches:raise ValueError('missing source '+needle)
    return matches[0]['source_id']
DOCV=source('Vector/l2_distance.md');DOCF=source('create-fulltext2-index.md');DOCJ=source('json_contains.md')
MYSQLM=source('func_math.test');MYSQLS=source('func_str.test');MYSQLT=source('func_time.test');MYSQLD=source('type_decimal.test');MYSQLQ=source('subselect.test')
ORGB=source('q01_daily_call_volume.sql','mo-benchmark');ORGF=source('prepare_fulltext_functional.py','mo-search-lab');ORGD=source('result/sql/ddl.sql','mo-auto-test');ORGREPLACE=source('cases/replace_into.sql','mo-nightly-regression')
ORGV=source('vector-contract-hardening-design.md','mo-nightly-regression');ORGFT2=source('fulltext2_stability/oracle.py','mo-nightly-regression')
def alphabet(n):
    s=''
    while n:s=chr(97+n%26)+s;n//=26
    return s or 'a'
def vector(i,d=3):return [((i*17+j*11)%101-50)/10 for j in range(d)]
def vstr(v):return '['+','.join(format(x,'.10g') for x in v)+']'
PATTERNS=['alpha beta fox','alpha gamma dog','beta gamma fox','alpha beta gamma rabbit','omega gamma cat','omega beta dog']
DOCS={i:'tok'+alphabet(i)+' '+PATTERNS[i%6] for i in range(1,201)}
SEED=[(i,i%17,i*3-200,None if i%7==0 else i%11,'name'+alphabet(i)) for i in range(1,201)]
cases=[];seen=set();familycounts=collections.Counter();modulecounts=collections.Counter()
def add(module,family,sql,params=None,expected=None,diff=True,expect_error=False,sources=None,mode='ordered',steps=None,tolerance=1e-6):
    statements=steps or [{'sql':sql,'params':params or []}]
    canonical=json.dumps(statements,sort_keys=True,ensure_ascii=False,separators=(',',':'));h=hashlib.sha256(canonical.encode()).hexdigest()
    if h in seen:return False
    seen.add(h);cid=f'C{len(cases)+1:05d}';cases.append({'id':cid,'module':module,'family':family,'statements':statements,'expected':expected,'mysql_differential':diff,'expect_error':expect_error,'compare_mode':mode,'tolerance':tolerance,'sources':sources or [],'sql_sha256':h});familycounts[family]+=1;modulecounts[module]+=1;return True
def fill(module,target,fn):
    j=0
    while modulecounts[module]<target:
        fn(j);j+=1
        if j>target*50:raise RuntimeError('not enough unique cases '+module)
    print(module,modulecounts[module],flush=True)
def numeric(j):
    a=rng.randint(-10000000,10000000);b=rng.randint(1,10000);k=j%16;src=[MYSQLM]
    if k==0:s,p,e,f='select %s+%s',[a,b],a+b,'number.add'
    elif k==1:s,p,e,f='select %s-%s',[a,b],a-b,'number.subtract'
    elif k==2:s,p,e,f='select %s*%s',[a,b],a*b,'number.multiply'
    elif k==3:s,p,e,f='select %s div %s',[a,b],math.trunc(a/b),'number.div'
    elif k==4:s,p,e,f='select mod(%s,%s)',[a,b],a-math.trunc(a/b)*b,'number.mod_signed'
    elif k==5:s,p,e,f='select abs(%s),sign(%s)',[a,a],[abs(a),(a>0)-(a<0)],'number.abs_sign'
    elif k==6:s,p,e,f='select floor(%s),ceiling(%s)',[a/100,a/100],[math.floor(a/100),math.ceil(a/100)],'number.floor_ceiling'
    elif k==7:s,p,e,f='select power(%s,2)',[a],a*a,'number.power'
    elif k==8:s,p,e,f='select sqrt(%s)',[abs(a)],math.sqrt(abs(a)),'number.sqrt'
    elif k==9:s,p,e,f='select greatest(%s,%s),least(%s,%s)',[a,b,a,b],[max(a,b),min(a,b)],'number.greatest_least'
    elif k==10:s,p,e,f='select %s/%s',[a,b],None,'number.divide'
    elif k==11:s,p,e,f='select round(cast(%s as decimal(20,4)),2)',[str(a/10000)],None,'number.decimal_round'
    elif k==12:s,p,e,f='select truncate(cast(%s as decimal(20,4)),2)',[str(a/10000)],None,'number.decimal_truncate'
    elif k==13:s,p,e,f='select log(%s),log2(%s),log10(%s)',[b,b,b],[math.log(b),math.log2(b),math.log10(b)],'number.log'
    elif k==14:s,p,e,f='select sin(%s),cos(%s)',[a/10000,a/10000],[math.sin(a/10000),math.cos(a/10000)],'number.trig'
    else:s,p,e,f='select %s & %s,%s | %s,%s ^ %s',[abs(a),b,abs(a),b,abs(a),b],[abs(a)&b,abs(a)|b,abs(a)^b],'number.bitwise'
    add('numeric',f,s,p,None if e is None else [e if isinstance(e,list) else [e]],sources=src)
def strings(j):
    a=rng.choice(['中文测试','alpha','MixedCase','😀火星','café','a b c','',"apostrophe'quote",'newline\nvalue'])+alphabet(j+1);b=alphabet(rng.randint(1,10000));k=j%18
    if k==0:s,p,e,f='select length(%s),char_length(%s)',[a,a],[len(a.encode()),len(a)],'string.bytes_chars'
    elif k==1:s,p,e,f='select concat(%s,%s)',[a,b],[a+b],'string.concat'
    elif k==2:s,p,e,f='select concat_ws(%s,%s,null,%s)',[b,a,b],[a+b+b],'string.concat_ws_null'
    elif k==3:s,p,e,f='select reverse(%s)',[a],[a[::-1]],'string.reverse_unicode'
    elif k==4:n=rng.randint(0,30);s,p,e,f='select left(%s,%s),right(%s,%s)',[a,n,a,n],[a[:n],a[-n:] if n else ''],'string.left_right'
    elif k==5:n=rng.randint(1,max(1,len(a)));s,p,e,f='select substring(%s,%s,3)',[a,n],[a[n-1:n+2]],'string.substring_positive'
    elif k==6:n=-rng.randint(1,max(1,len(a)));s,p,e,f='select substring(%s,%s,3)',[a,n],[a[len(a)+n:len(a)+n+3]],'string.substring_negative'
    elif k==7:s,p,e,f='select replace(%s,%s,%s)',[a,'a',b],[a.replace('a',b)],'string.replace'
    elif k==8:s,p,e,f='select trim(%s)',['  '+a+'  '],[a.strip(' ')],'string.trim_spaces'
    elif k==9:s,p,e,f='select lower(%s),upper(%s)',[a,a],[a.lower(),a.upper()],'string.case_unicode'
    elif k==10:n=j%6;s,p,e,f='select repeat(%s,%s)',[a,n],[a*n],'string.repeat'
    elif k==11:s,p,e,f='select locate(%s,%s)',[b,a+b],[(a+b).find(b)+1],'string.locate_unicode'
    elif k==12:s,p,e,f='select hex(%s)',[a],[a.encode().hex().upper()],'string.hex'
    elif k==13:s,p,e,f='select strcmp(%s,%s)',[b,b],[0],'string.strcmp_equal'
    elif k==14:s,p,e,f='select ascii(%s)',[b],[ord(b[0])],'string.ascii'
    elif k==15:n=len(a)+j%5;s,p,e,f='select lpad(%s,%s,%s),rpad(%s,%s,%s)',[a,n,b,a,n,b],None,'string.pad_multichar'
    elif k==16:s,p,e,f='select find_in_set(%s,%s)',[b,'x,'+b+',z'],[['x',b,'z'].index(b)+1],'string.find_in_set'
    else:s,p,e,f='select substring_index(%s,%s,%s)',[a+b+a,b,1],[(a+b+a).split(b)[0]],'string.substring_index'
    add('strings',f,s,p,None if e is None else [e],sources=[MYSQLS])
def types(j):
    k=j%12;a=rng.randint(-1000000000,1000000000);src=[MYSQLD]
    if k==0:s,p,e,f='select cast(%s as signed)',[str(a)],[[a]],'type.cast_signed'
    elif k==1:s,p,e,f='select cast(%s as unsigned)',[str(abs(a))],[[abs(a)]],'type.cast_unsigned'
    elif k==2:s,p,e,f='select cast(%s as decimal(20,4))',[str(a/10000)],None,'type.cast_decimal'
    elif k==3:s,p,e,f='select cast(%s as char)',[a],[[str(a)]],'type.cast_char'
    elif k==4:s,p,e,f='select coalesce(null,%s,%s),ifnull(null,%s)',[a,j,a],[[a,a]],'type.coalesce_null'
    elif k==5:s,p,e,f='select nullif(%s,%s)',[a,a],[[None]],'type.nullif_equal'
    elif k==6:s,p,e,f='select case when %s<0 then -1 when %s=0 then 0 else 1 end',[a,a],[[((a>0)-(a<0))]],'type.case_signed'
    elif k==7:s,p,e,f='select %s is null,%s is not null,null <=> %s',[a,a,a],[[0,1,0]],'type.null_safe'
    elif k==8:s,p,e,f='select if(%s>0,%s,%s)',[a,a,-a],[[abs(a)]],'type.if_branch'
    elif k==9:s,p,e,f='select cast(%s as decimal(25,4))+cast(%s as decimal(25,4))',[str(a/10000),str(j/10000)],None,'type.decimal_add'
    elif k==10:s,p,e,f='select cast(%s as double)',[str(a/100)],[[a/100]],'type.cast_double'
    else:s,p,e,f='select cast(%s as float)',[str(a/100)],None,'type.cast_float'
    add('types',f,s,p,e,sources=src,tolerance=5e-6 if f=='type.cast_float' else 1e-6)
def dates(j):
    d=datetime.date(2000,1,1)+datetime.timedelta(days=rng.randint(0,15000));b=rng.randint(-500,500);v=str(d);k=j%10
    if k==0:s,p,e,f='select year(%s),month(%s),day(%s)',[v,v,v],[[d.year,d.month,d.day]],'date.parts'
    elif k==1:s,p,e,f='select date_add(%s,interval %s day)',[v,b],[[str(d+datetime.timedelta(days=b))]],'date.add_day'
    elif k==2:s,p,e,f='select date_sub(%s,interval %s day)',[v,b],[[str(d-datetime.timedelta(days=b))]],'date.subtract_day'
    elif k==3:s,p,e,f='select datediff(%s,%s)',[v,str(d+datetime.timedelta(days=b))],[[-b]],'date.diff'
    elif k==4:s,p,e,f='select dayofweek(%s),weekday(%s)',[v,v],[[((d.weekday()+1)%7)+1,d.weekday()]],'date.weekday'
    elif k==5:s,p,e,f='select dayofyear(%s)',[v],[[d.timetuple().tm_yday]],'date.dayofyear'
    elif k==6:s,p,e,f="select date_format(%s,'%Y-%m-%d')",[v],[[v]],'date.format'
    elif k==7:s,p,e,f="select str_to_date(%s,'%Y-%m-%d')",[v],[[v]],'date.parse'
    elif k==8:s,p,e,f='select last_day(%s)',[v],None,'date.last_day'
    else:s,p,e,f='select timestampdiff(day,%s,%s)',[v,str(d+datetime.timedelta(days=b))],[[b]],'date.timestampdiff'
    # PyMySQL interpolates literal % format characters too.
    s=s.replace("'%Y-%m-%d'","'%%Y-%%m-%%d'")
    add('dates',f,s,p,e,sources=[MYSQLT])
def relational(j):
    lo=rng.randint(0,210);hi=lo+rng.randint(0,180);g=rng.randint(0,16);n=rng.randint(1,30);offset=rng.randint(0,20);k=j%16;src=[MYSQLQ,ORGB]
    rows=[r for r in SEED if lo<=r[0]<=hi]
    if k==0:s,p,e,f='select count(*),coalesce(sum(val),0) from seed where id between %s and %s',[lo,hi],[[len(rows),sum(r[2] for r in rows)]],'rel.range_aggregate'
    elif k==1:s,p,e,f='select id from seed where id between %s and %s order by id limit %s offset %s',[lo,hi,n,offset],[[r[0]] for r in rows[offset:offset+n]],'rel.limit_offset'
    elif k==2:s,p,e,f='select count(*) from seed a join seed b on a.grp=b.grp where a.id between %s and %s and b.grp=%s',[lo,hi,g],[[sum(1 for a in rows for b in SEED if a[1]==b[1]==g)]],'rel.self_join'
    elif k==3:s,p,e,f='select a.id from seed a where a.id between %s and %s and exists(select 1 from seed b where b.grp=a.grp and b.id>%s) order by a.id',[lo,hi,offset*10],[[a[0]] for a in rows if any(b[1]==a[1] and b[0]>offset*10 for b in SEED)],'rel.correlated_exists'
    elif k==4:s,p,e,f='select id from seed where id between %s and %s and grp in(select grp from seed where id=%s) order by id',[lo,hi,g+1],[[a[0]] for a in rows if a[1]==(g+1)%17],'rel.in_subquery'
    elif k==5:s,p,e,f='select grp,count(*),sum(val) from seed where id between %s and %s group by grp having count(*)>=%s order by grp',[lo,hi,n],[[x,len([a for a in rows if a[1]==x]),sum(a[2] for a in rows if a[1]==x)] for x in range(17) if len([a for a in rows if a[1]==x])>=n],'rel.group_having'
    elif k==6:s,p,e,f='with c as(select id,val from seed where id between %s and %s) select count(*),coalesce(sum(val),0) from c',[lo,hi],[[len(rows),sum(a[2] for a in rows)]],'rel.cte'
    elif k==7:s,p,e,f='select id,row_number() over(order by id) from seed where id between %s and %s order by id',[lo,hi],[[a[0],i+1] for i,a in enumerate(rows)],'rel.window_row_number'
    elif k==8:s,p,e,f='select id,sum(val) over(order by id rows between unbounded preceding and current row) from seed where id between %s and %s order by id',[lo,hi],[[a[0],sum(b[2] for b in rows[:i+1])] for i,a in enumerate(rows)],'rel.window_prefix_sum'
    elif k==9:s,p,e,f='select count(nullable),count(*) from seed where id between %s and %s',[lo,hi],[[sum(a[3] is not None for a in rows),len(rows)]],'rel.null_count'
    elif k==10:s,p,e,f='select id from seed where id between %s and %s and nullable not in(%s,null) order by id',[lo,hi,g],[],'rel.not_in_null'
    elif k==11:s,p,e,f='select a.id,b.id from seed a left join seed b on b.id=a.id+%s where a.id between %s and %s order by a.id',[n,lo,hi],[[a[0],a[0]+n if a[0]+n<=200 else None] for a in rows],'rel.left_join_missing'
    elif k==12:s,p,e,f='select distinct grp from seed where id between %s and %s order by grp',[lo,hi],[[x] for x in sorted({a[1] for a in rows})],'rel.distinct'
    elif k==13:s,p,e,f='select id from seed where id between %s and %s union select id from seed where grp=%s order by id',[lo,hi,g],[[x] for x in sorted({a[0] for a in rows}|{a[0] for a in SEED if a[1]==g})],'rel.union'
    elif k==14:s,p,e,f='select id from seed where id between %s and %s and (grp=%s or nullable is null) order by id',[lo,hi,g],[[a[0]] for a in rows if a[1]==g or a[3] is None],'rel.or_null'
    else:s,p,e,f='select (select count(*) from seed where id between %s and %s),%s',[lo,hi,g],[[len(rows),g]],'rel.scalar_subquery'
    add('relational',f,s,p,e,sources=src)
def jsoncases(j):
    a=rng.randint(-1000000,1000000);b=alphabet(j+1);obj={'a':a,'text':b,'items':[a,a+1,None],'nested':{'flag':True}};v=json.dumps(obj,ensure_ascii=False);k=j%12;mode='ordered'
    if k==0:s,p,e,f='select json_extract(%s,%s)',[v,'$.a'],[[a]],'json.extract_scalar';mode='json'
    elif k==1:s,p,e,f='select json_unquote(json_extract(%s,%s))',[v,'$.text'],[[b]],'json.unquote'
    elif k==2:s,p,e,f='select json_valid(%s)',[v],[[1]],'json.valid'
    elif k==3:s,p,e,f='select json_length(%s),json_length(%s,%s)',[v,v,'$.items'],[[4,3]],'json.length'
    elif k==4:s,p,e,f='select json_type(json_extract(%s,%s))',[v,'$.items'],[['ARRAY']],'json.type'
    elif k==5:s,p,e,f='select json_contains(%s,%s,%s)',[v,str(a),'$.items'],[[1]],'json.contains_present'
    elif k==6:s,p,e,f='select json_contains(%s,%s,%s)',[v,str(a+2000000),'$.items'],[[0]],'json.contains_absent'
    elif k==7:s,p,e,f='select json_extract(%s,%s)',[v,'$.missing'+b],[[None]],'json.missing';mode='json'
    elif k==8:s,p,e,f='select json_array(%s,%s,null)',[a,b],[[[a,b,None]]],'json.array';mode='json'
    elif k==9:s,p,e,f='select json_object(%s,%s,%s,%s)',['n',a,'s',b],[[{'n':a,'s':b}]],'json.object';mode='json'
    elif k==10:s,p,e,f='select json_overlaps(%s,%s)',[json.dumps([a,a+1]),json.dumps([a+1,a+2])],[[1]],'json.overlaps'
    else:s,p,e,f='select json_contains_path(%s,%s,%s)',[v,'one','$.nested.flag'],[[1]],'json.contains_path'
    add('json',f,s,p,e,sources=[DOCJ],mode=mode)
def vectors(j):
    d=[2,3,4,8,16,32,64][j%7];a=[rng.randint(-100,100)/8 for _ in range(d)];b=[rng.randint(-100,100)/8 for _ in range(d)];x=vstr(a);y=vstr(b);k=j%12;typ='vecf64' if j%2 else 'vecf32';cast=lambda v:f'cast(%s as {typ}({d}))';left=cast(x);right=cast(y)
    if k==0:s,p,e,f=f'select l2_distance({left},{right})',[x,y],[[math.sqrt(sum((u-v)**2 for u,v in zip(a,b)))]],'vector.l2'
    elif k==1:s,p,e,f=f'select l2_distance_sq({left},{right})',[x,y],[[sum((u-v)**2 for u,v in zip(a,b))]],'vector.l2sq'
    elif k==2:s,p,e,f=f'select inner_product({left},{right})',[x,y],[[-sum(u*v for u,v in zip(a,b))]],'vector.dot'
    elif k==3:s,p,e,f=f'select l1_norm({left}),l2_norm({left})',[x,x],[[sum(abs(u) for u in a),math.sqrt(sum(u*u for u in a))]],'vector.norm'
    elif k==4:
        norm=math.sqrt(sum(u*u for u in a)*sum(v*v for v in b));e=[[1-sum(u*v for u,v in zip(a,b))/norm]] if norm else [[1]];s,p,f=f'select cosine_distance({left},{right})',[x,y],'vector.cosine'
    elif k==5:s,p,e,f=f'select vector_dims({left})',[x],[[d]],'vector.dimensions'
    elif k==6:s,p,e,f=f'select l2_distance({left},{left})',[x,x],[[0]],'vector.self_zero'
    elif k==7:s,p,e,f=f'select l2_distance({left},{right}),l2_distance({right},{left})',[x,y,y,x],[[math.sqrt(sum((u-v)**2 for u,v in zip(a,b)))]*2],'vector.symmetry'
    elif k==8:
        a=vector(j,3);b=vector(j+7,3);s,p,e,f='select l2_distance(v,%s) from vectors where id=%s',[vstr(b),j%200+1],[[math.sqrt(sum((u-w)**2 for u,w in zip(vector(j%200+1,3),b)))]],'vector.column_batch'
    elif k==9:s,p,e,f=f'select l2_distance(normalize_l2({left}),normalize_l2({left}))',[x,x],[[0]],'vector.normalize_identity'
    elif k==10:s,p,e,f=f'select l2_distance({left},null)',[x],[[None]],'vector.null'
    else:s,p,e,f=f'select l1_distance({left},{right})',[x,y],[[sum(abs(u-v) for u,v in zip(a,b))]],'vector.l1'
    if j%20==0:
        bad=vstr(json.loads(x)[:-1]);s=f'select cast(%s as {typ}({d}))';p=[bad];e=None;f='vector.reject_dimensions'
        add('vectors',f,s,p,e,diff=False,expect_error=True,sources=[DOCV,ORGV]);return
    if j%20==1:
        table='vh' if j%40==1 else 'vi';q=vstr(vector(j+29));kk=1+j%13
        threshold=sorted(math.sqrt(sum((u-w)**2 for u,w in zip(vector(i),vector(j+29)))) for i in range(1,201))[kk-1]
        add('vectors','vector.ann_'+table,f'select id,l2_distance(v,%s) from {table} order by l2_distance(v,%s) limit {kk}',[q,q],{'query':vector(j+29),'k':kk,'cutoff':threshold},diff=False,sources=[DOCV,ORGV],mode='ann',tolerance=2e-5);return
    add('vectors',f,s,p,e,diff=False,sources=[DOCV,ORGV],tolerance=2e-5)
def fulltexts(j):
    if j%20==0:
        parser=rng.choice(['ngram','gojieba']);choices=[('苹果',[1,2,3]),('苹果 香蕉',[1,2,3,4]),('+苹果 +香蕉',[1,2]),('"苹果 香蕉"',[1]),('大学怎么网上选宿舍',[5]),('火星飞船',[])];q,ids=choices[(j//20)%6];lo=rng.randint(0,6);hi=lo+rng.randint(1,7)
        add('fulltext','fulltext.cjk_'+parser,f'select id from fc_{parser} where match(body) against(%s in boolean mode) and id between %s and %s order by id',[q,lo,hi],[[i] for i in ids if lo<=i<=hi],diff=False,sources=[ORGF,DOCF]);return
    tid=rng.randint(1,200);other=rng.randint(1,200);term='tok'+alphabet(tid);word=rng.choice(['alpha','beta','gamma','fox','dog','omega']);lo=rng.randint(0,200);hi=lo+rng.randint(1,200);kind=j%8;t='ft2' if j%2 else 'ft';mode=' in boolean mode'
    if kind==0:q='+'+term+' +'+word;found=[i for i,b in DOCS.items() if term in b.split() and word in b.split()];f='fulltext.must'
    elif kind==1:q='+'+term+' -'+word;found=[i for i,b in DOCS.items() if term in b.split() and word not in b.split()];f='fulltext.must_not'
    elif kind==2:q=term+' tok'+alphabet(other);found=[i for i,b in DOCS.items() if term in b.split() or 'tok'+alphabet(other) in b.split()];f='fulltext.or'
    elif kind==3:q='"'+term+' '+word+'"';found=[i for i,b in DOCS.items() if term+' '+word in b];f='fulltext.phrase'
    elif kind==4:q='+'+term+' +'+term;found=[tid];f='fulltext.duplicate_must'
    elif kind==5:q=term;found=[tid];f='fulltext.single'
    elif kind==6:q='+'+term+' +missing'+alphabet(j+1);found=[];f='fulltext.missing_intersection'
    else:q=term+' '+word;mode='' if t=='ft2' else ' in boolean mode';found=[i for i,b in DOCS.items() if term+' '+word in b] if t=='ft2' else [i for i,b in DOCS.items() if term in b.split() or word in b.split()];f='fulltext.natural_phrase_or_boolean'
    expected=[[i] for i in sorted(found) if lo<=i<=hi];sql=f'select id from {t} where match(body) against(%s{mode}) and id between %s and %s order by id'
    add('fulltext',f,sql,[q,lo,hi],expected,diff=False,sources=[DOCF,ORGF,ORGFT2])
def ddl(j):
    t='{table}';a=rng.randint(-1000000,1000000);b='value'+alphabet(j+1);k=j%10;steps=[{'sql':f'create table {t}(id bigint primary key,n bigint,body varchar(200))'}]
    def step(s,p=None):steps.append({'sql':s,'params':p or []})
    step(f'insert into {t} values(1,%s,%s)',[a,b])
    if k==0:step(f'alter table {t} add column extra int default %s',[j%101]);step(f'select id,n,body,extra from {t}');e=[[1,a,b,j%101]];f='ddl.add_default'
    elif k==1:step(f'create index idx on {t}(n)');step(f'select id,n from {t} where n=%s',[a]);e=[[1,a]];f='ddl.secondary_index'
    elif k==2:step(f'begin');step(f'update {t} set n=%s',[a+10]);step('rollback');step(f'select n from {t}');e=[[a]];f='txn.rollback_update'
    elif k==3:step('begin');step(f'update {t} set n=%s',[a+10]);step('commit');step(f'select n from {t}');e=[[a+10]];f='txn.commit_update'
    elif k==4:step(f'replace into {t} values(1,%s,%s)',[a+20,b+'replaced']);step(f'select n,body from {t}');e=[[a+20,b+'replaced']];f='dml.replace_primary'
    elif k==5:step(f'insert into {t} values(1,%s,%s) on duplicate key update n=values(n)',[a+30,b]);step(f'select n from {t}');e=[[a+30]];f='dml.upsert'
    elif k==6:step('begin');step(f'delete from {t}');step('rollback');step(f'select n from {t}');e=[[a]];f='txn.rollback_delete'
    elif k==7:step(f'create unique index uq on {t}(body)');step(f'select n from {t} where body=%s',[b]);e=[[a]];f='ddl.unique_index'
    elif k==8:step(f'alter table {t} modify body varchar(400)');step(f'select body from {t}');e=[[b]];f='ddl.widen_varchar'
    else:step(f'truncate table {t}');step(f'select count(*) from {t} where n=%s',[a]);e=[[0]];f='ddl.truncate'
    add('ddl_transactions',f,None,expected=e,steps=steps,sources=[ORGD,ORGREPLACE,source('insert.test')])
def compatibility(j):
    a=rng.randint(-10000000,10000000);b=rng.randint(1,1000000);k=j%10
    if k==0:s,p,e,f='select %s between %s and %s',[a,-b,b],[[int(-b<=a<=b)]],'boundary.between'
    elif k==1:s,p,e,f='select (%s<%s) is true,(%s<%s) is false',[a,b,a,b],[[int(a<b),int(a>=b)]],'boundary.boolean_is'
    elif k==2:s,p,e,f='select %s in(%s,%s,null)',[a,a,b],[[1]],'boundary.in_null_present'
    elif k==3:s,p,e,f='select %s in(%s,null)',[a,b],[[1 if a==b else None]],'boundary.in_null_absent'
    elif k==4:s,p,e,f='select %s/0',[a],[[None]],'boundary.division_zero'
    elif k==5:s,p,e,f='select greatest(%s,null),least(%s,null)',[a,b],[[None,None]],'boundary.greatest_null'
    elif k==6:s,p,e,f='select nullif(%s,%s)',[a,b],[[None if a==b else a]],'boundary.nullif_distinct'
    elif k==7:s,p,e,f='select abs(cast(%s as decimal(30,0)))',[str(-(2**63)+j)],[[abs(-(2**63)+j)]],'boundary.decimal_int64'
    elif k==8:s,p,e,f='select cast(%s as unsigned)',[str(2**64-1-j)],[[2**64-1-j]],'boundary.uint64'
    else:s,p,e,f='select round(cast(%s as decimal(30,10)),5)',[str(a/10000)],None,'boundary.decimal_round'
    add('compatibility',f,s,p,e,sources=[MYSQLM,MYSQLD])
fill('numeric',5000,numeric);fill('strings',7000,strings);fill('types',5000,types);fill('dates',3000,dates);fill('relational',10000,relational);fill('json',4000,jsoncases);fill('vectors',6000,vectors);fill('fulltext',4000,fulltexts);fill('ddl_transactions',3500,ddl)
# Exact, public MySQL scalar statements are preserved as standalone cases.
def split_statements(text):
    quote=None;start=0;i=0
    while i<len(text):
        ch=text[i]
        if quote:
            if ch=='\\':i+=2;continue
            if ch==quote:
                if i+1<len(text) and text[i+1]==quote:i+=2;continue
                quote=None
        elif ch in ['\"',"'",'`']:quote=ch
        elif ch==';':yield text[start:i];start=i+1
        i+=1
allowed=set('abs sign floor ceil ceiling truncate round log ln log2 log10 exp pow power sqrt pi sin cos tan cot asin acos atan atan2 degrees radians mod greatest least cast convert decimal char float double binary signed unsigned bit_count hex unhex length octet_length char_length character_length concat concat_ws locate instr left right substring substr mid trim ltrim rtrim lpad rpad lower upper reverse replace strcmp ascii ord find_in_set substring_index space format elt field make_set repeat date time year month day dayofmonth dayofweek dayofyear weekday week weekofyear yearweek date_add date_sub adddate subdate datediff timediff timestampdiff timestampadd date_format time_format str_to_date last_day makedate maketime hour minute second microsecond extract quarter to_days from_days to_seconds unix_timestamp from_unixtime coalesce ifnull nullif if isnull json_extract json_unquote json_valid json_length json_type json_contains json_contains_path json_keys json_array json_object json_overlaps json_remove json_merge_patch json_merge_preserve json_pretty json_value json_depth'.split())
for m in [v for v in M if v['repo']=='mysql/mysql-server' and v['path'].endswith('.test')]:
    text=Path(m['local_path']).read_text(errors='replace');text='\n'.join(l for l in text.splitlines() if not l.lstrip().startswith(('#','--')))
    for stmt in split_statements(text):
        stmt=stmt.strip()
        if not re.match(r'^select\s',stmt,re.I) or len(stmt)>1600:continue
        if re.search(r'\b(from|into|benchmark|sleep|load_file|rand|uuid|now|sysdate|current_timestamp|connection_id|version|repeat)\b|@|\$|\\',stmt,re.I):continue
        calls={x.lower() for x in re.findall(r'([a-zA-Z_][a-zA-Z_0-9]*)\s*\(',stmt)}
        if not calls.issubset(allowed):continue
        if re.search(r'\b(lpad|rpad|space|concat)\s*\(',stmt,re.I) and any(int(n)>65535 for n in re.findall(r'(?<![a-zA-Z_])\b[0-9]+\b',stmt)):continue
        if modulecounts['compatibility']>=1000:break
        add('compatibility','mysql.public_scalar',stmt,None,None,sources=[m['source_id']])
fill('compatibility',2500,compatibility)
assert len(cases)==50000 and len(seen)==50000
with open(P/'cases.jsonl','w') as f:
    for c in cases:f.write(json.dumps(c,ensure_ascii=False,separators=(',',':'))+'\n')
(P/'coverage.json').write_text(json.dumps({'total':len(cases),'unique_sql_and_parameters':len(seen),'modules':modulecounts,'families':familycounts,'family_count':len(familycounts),'mysql_differential_cases':sum(c['mysql_differential'] for c in cases),'python_oracle_cases':sum(c['expected'] is not None for c in cases),'public_mysql_exact_cases':familycounts['mysql.public_scalar'],'source_usage':dict(collections.Counter(s for c in cases for s in c['sources']))},ensure_ascii=False,indent=2))
(P/'fixtures.json').write_text(json.dumps({'seed':SEED,'docs':DOCS,'vectors':[(i,vstr(vector(i))) for i in range(1,201)]},ensure_ascii=False))
print('total',len(cases),'families',len(familycounts),'public mysql',familycounts['mysql.public_scalar'],flush=True)

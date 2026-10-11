-- Run once in a new, dedicated database; this file does not drop existing data.
create database mo_ft2_cache_boundary;
use mo_ft2_cache_boundary;
set experimental_fulltext2_index=1;
create table early(id bigint primary key,body text);
create table late(id bigint primary key,body text);
insert into early values(1,'coldbasetoken');
insert into late values(1,'coldbasetoken');
create fulltext2 index txt on early(body);
create fulltext2 index txt on late(body);
-- Warm only early before the write.
select id from early where match(body) against('coldbasetoken');
insert into early values(2,'cachefreshterm');
insert into late values(2,'cachefreshterm');
-- Resolve each hidden index table and poll its durable CDC readiness.
set @early_storage=(select index_table_name from mo_catalog.mo_indexes where name='txt' and algo='fulltext2' and algo_table_type='ftv2_index' and table_id in(select rel_id from mo_catalog.mo_tables where reldatabase=database() and relname='early') limit 1);
set @late_storage=(select index_table_name from mo_catalog.mo_indexes where name='txt' and algo='fulltext2' and algo_table_type='ftv2_index' and table_id in(select rel_id from mo_catalog.mo_tables where reldatabase=database() and relname='late') limit 1);
set @ready_sql=concat('select (select coalesce(max(chunk_id),-1)>=0 from `',@early_storage,'` where index_id=''cdc_tail'' and tag=1) as early_ready,(select coalesce(max(chunk_id),-1)>=0 from `',@late_storage,'` where index_id=''cdc_tail'' and tag=1) as late_ready');
prepare readiness from @ready_sql;
-- Repeat EXECUTE until both columns are 1; do not MATCH while waiting.
execute readiness;
-- After readiness, both tables should return id=2. Observed: early empty, late=2.
select id from early where match(body) against('cachefreshterm');
select id from late where match(body) against('cachefreshterm');
alter table early alter reindex txt fulltext2 force_sync;
-- The rebuild restores early to id=2.
select id from early where match(body) against('cachefreshterm');
deallocate prepare readiness;

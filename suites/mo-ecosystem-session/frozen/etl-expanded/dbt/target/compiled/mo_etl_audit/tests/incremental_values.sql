select 1 as mismatch where
  (select count(*) from `etl_dbt`.`incremental_rows`) <> 3
  or (select amount from `etl_dbt`.`incremental_rows` where id=2) <> -113.56
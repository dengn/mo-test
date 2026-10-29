select 1 as mismatch where
  (select count(*) from `etl_dbt_adapted`.`incremental_rows`) <> 4
  or (select amount from `etl_dbt_adapted`.`incremental_rows` where id=2) <> -157.80
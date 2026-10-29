select 1 as mismatch where
  (select count(*) from `etl_dbt_adapted`.`view_rows`) <> 3
  or (select amount from `etl_dbt_adapted`.`view_rows` where id=1) <> 24.68
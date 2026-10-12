select 1 as mismatch where
  (select count(*) from `etl_dbt_adapted`.`transformed`) <> 4
  or (select amount from `etl_dbt_adapted`.`transformed` where id=1) <> 24.68
  or (select amount from `etl_dbt_adapted`.`transformed` where id=2) <> -157.80
  or (select label from `etl_dbt_adapted`.`transformed` where id=1) <> '中文'
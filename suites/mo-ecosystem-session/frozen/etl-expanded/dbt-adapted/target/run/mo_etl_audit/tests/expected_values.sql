select
      count(*) as failures,
      case
        when count(*) <> 0 then 'true'
        else 'false'
      end as should_warn,
      case
        when count(*) <> 0 then 'true'
        else 'false'
      end as should_error
    from (
      select 1 as mismatch where
  (select count(*) from `etl_dbt_adapted`.`transformed`) <> 4
  or (select amount from `etl_dbt_adapted`.`transformed` where id=1) <> 24.68
  or (select amount from `etl_dbt_adapted`.`transformed` where id=2) <> -157.80
  or (select label from `etl_dbt_adapted`.`transformed` where id=1) <> '中文'
      
    ) dbt_internal_test
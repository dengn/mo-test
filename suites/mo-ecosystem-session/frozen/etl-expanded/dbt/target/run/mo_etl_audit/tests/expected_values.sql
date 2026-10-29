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
  (select count(*) from `etl_dbt`.`transformed`) <> 3
  or (select amount from `etl_dbt`.`transformed` where id=1) <> 24.68
  or (select amount from `etl_dbt`.`transformed` where id=2) <> -113.56
  or (select label from `etl_dbt`.`transformed` where id=1) <> '中文'
      
    ) dbt_internal_test
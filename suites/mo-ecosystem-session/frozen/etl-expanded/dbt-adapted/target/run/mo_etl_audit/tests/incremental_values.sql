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
  (select count(*) from `etl_dbt_adapted`.`incremental_rows`) <> 4
  or (select amount from `etl_dbt_adapted`.`incremental_rows` where id=2) <> -157.80
      
    ) dbt_internal_test
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
  (select count(*) from `etl_dbt_adapted`.`view_rows`) <> 3
  or (select amount from `etl_dbt_adapted`.`view_rows` where id=1) <> 24.68
      
    ) dbt_internal_test
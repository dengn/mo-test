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
      select case_id,id,count(*) AS n from `orchestrator10000`.`out_json_scalar` group by case_id,id having count(*)<>1
      
    ) dbt_internal_test

  
    

  create  table
    `etl_dbt_adapted`.`transformed__dbt_tmp`
    
    
      as
    
    (
      select id, upper(label) as label, cast(amount * 2 as decimal(18,2)) as amount from `etl_dbt_adapted`.`source_rows`
    )

  
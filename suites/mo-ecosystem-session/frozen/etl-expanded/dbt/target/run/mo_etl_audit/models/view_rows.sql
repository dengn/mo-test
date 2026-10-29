
  create view `etl_dbt`.`view_rows__dbt_tmp`
    
    
  as (
    
select id,label,amount from `etl_dbt`.`transformed` where amount>0
  );
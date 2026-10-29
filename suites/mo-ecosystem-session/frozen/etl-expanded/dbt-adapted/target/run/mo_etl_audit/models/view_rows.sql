
    create or replace view `etl_dbt_adapted`.`view_rows` as 
select id,label,amount from `etl_dbt_adapted`.`transformed` where amount>0
  
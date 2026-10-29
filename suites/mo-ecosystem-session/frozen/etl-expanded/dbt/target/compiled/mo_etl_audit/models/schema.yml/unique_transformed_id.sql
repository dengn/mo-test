
    
    

select
    id as unique_field,
    count(*) as n_records

from `etl_dbt`.`transformed`
where id is not null
group by id
having count(*) > 1



select case_id,id,count(*) AS n from {{ref('out_time6')}} group by case_id,id having count(*)<>1

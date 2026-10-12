select case_id,id,count(*) AS n from {{ref('out_json_scalar')}} group by case_id,id having count(*)<>1

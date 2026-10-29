select case_id,id,count(*) AS n from {{ref('out_tinyint')}} group by case_id,id having count(*)<>1

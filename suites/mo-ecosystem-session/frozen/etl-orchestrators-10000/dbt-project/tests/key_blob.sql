select case_id,id,count(*) AS n from {{ref('out_blob')}} group by case_id,id having count(*)<>1

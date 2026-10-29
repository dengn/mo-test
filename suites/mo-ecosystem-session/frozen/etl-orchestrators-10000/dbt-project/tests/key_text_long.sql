select case_id,id,count(*) AS n from {{ref('out_text_long')}} group by case_id,id having count(*)<>1

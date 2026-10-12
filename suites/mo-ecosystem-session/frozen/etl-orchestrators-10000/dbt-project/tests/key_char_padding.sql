select case_id,id,count(*) AS n from {{ref('out_char_padding')}} group by case_id,id having count(*)<>1

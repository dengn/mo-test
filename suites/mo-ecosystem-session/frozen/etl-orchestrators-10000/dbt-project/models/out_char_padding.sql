SELECT b.case_id,b.id,
CASE WHEN incoming.id IS NOT NULL THEN incoming.v ELSE b.v END AS v,
CASE WHEN b.case_id BETWEEN 571 AND 580 THEN CONCAT(b.label,'→ETL',CAST(b.case_id-571 AS CHAR)) WHEN incoming.id IS NOT NULL THEN incoming.label ELSE b.label END AS label,
CASE WHEN b.case_id BETWEEN 571 AND 580 THEN b.rev+b.case_id-571+1 WHEN incoming.id IS NOT NULL THEN incoming.rev ELSE b.rev END AS rev
FROM `orchestrator10000`.`dbt_char_padding` AS b LEFT JOIN `orchestrator10000`.`dbt_delta_char_padding` AS incoming ON b.case_id=incoming.case_id AND b.id=incoming.id
WHERE (b.case_id NOT BETWEEN 571 AND 580 OR MOD(b.id,2)=MOD(b.case_id-571,2)) AND (b.case_id NOT BETWEEN 591 AND 600 OR (b.id<>1 AND b.id<(SELECT MAX(z.id)-1 FROM `orchestrator10000`.`dbt_char_padding` AS z WHERE z.case_id=b.case_id)) OR (b.case_id BETWEEN 591 AND 600 AND b.id=(SELECT MAX(z.id) FROM `orchestrator10000`.`dbt_char_padding` AS z WHERE z.case_id=b.case_id)))
UNION ALL SELECT incoming.case_id,incoming.id,incoming.v,incoming.label,incoming.rev FROM `orchestrator10000`.`dbt_delta_char_padding` AS incoming LEFT JOIN `orchestrator10000`.`dbt_char_padding` AS original ON original.case_id=incoming.case_id AND original.id=incoming.id WHERE original.id IS NULL

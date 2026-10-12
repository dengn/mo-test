SELECT b.case_id,b.id,
CASE WHEN incoming.id IS NOT NULL THEN incoming.v ELSE b.v END AS v,
CASE WHEN b.case_id BETWEEN 21 AND 30 THEN CONCAT(b.label,'→ETL',CAST(b.case_id-21 AS CHAR)) WHEN incoming.id IS NOT NULL THEN incoming.label ELSE b.label END AS label,
CASE WHEN b.case_id BETWEEN 21 AND 30 THEN b.rev+b.case_id-21+1 WHEN incoming.id IS NOT NULL THEN incoming.rev ELSE b.rev END AS rev
FROM `orchestrator10000`.`dbt_tinyint` AS b LEFT JOIN `orchestrator10000`.`dbt_delta_tinyint` AS incoming ON b.case_id=incoming.case_id AND b.id=incoming.id
WHERE (b.case_id NOT BETWEEN 21 AND 30 OR MOD(b.id,2)=MOD(b.case_id-21,2)) AND (b.case_id NOT BETWEEN 41 AND 50 OR (b.id<>1 AND b.id<(SELECT MAX(z.id)-1 FROM `orchestrator10000`.`dbt_tinyint` AS z WHERE z.case_id=b.case_id)) OR (b.case_id BETWEEN 41 AND 50 AND b.id=(SELECT MAX(z.id) FROM `orchestrator10000`.`dbt_tinyint` AS z WHERE z.case_id=b.case_id)))
UNION ALL SELECT incoming.case_id,incoming.id,incoming.v,incoming.label,incoming.rev FROM `orchestrator10000`.`dbt_delta_tinyint` AS incoming LEFT JOIN `orchestrator10000`.`dbt_tinyint` AS original ON original.case_id=incoming.case_id AND original.id=incoming.id WHERE original.id IS NULL
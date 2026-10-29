
  
    

  create  table
    `orchestrator10000`.`out_boolean__dbt_tmp`
    
    
      as
    
    (
      SELECT b.case_id,b.id,
CASE WHEN incoming.id IS NOT NULL THEN incoming.v ELSE b.v END AS v,
CASE WHEN b.case_id BETWEEN 471 AND 480 THEN CONCAT(b.label,'→ETL',CAST(b.case_id-471 AS CHAR)) WHEN incoming.id IS NOT NULL THEN incoming.label ELSE b.label END AS label,
CASE WHEN b.case_id BETWEEN 471 AND 480 THEN b.rev+b.case_id-471+1 WHEN incoming.id IS NOT NULL THEN incoming.rev ELSE b.rev END AS rev
FROM `orchestrator10000`.`dbt_boolean` AS b LEFT JOIN `orchestrator10000`.`dbt_delta_boolean` AS incoming ON b.case_id=incoming.case_id AND b.id=incoming.id
WHERE (b.case_id NOT BETWEEN 471 AND 480 OR MOD(b.id,2)=MOD(b.case_id-471,2)) AND (b.case_id NOT BETWEEN 491 AND 500 OR (b.id<>1 AND b.id<(SELECT MAX(z.id)-1 FROM `orchestrator10000`.`dbt_boolean` AS z WHERE z.case_id=b.case_id)) OR (b.case_id BETWEEN 491 AND 500 AND b.id=(SELECT MAX(z.id) FROM `orchestrator10000`.`dbt_boolean` AS z WHERE z.case_id=b.case_id)))
UNION ALL SELECT incoming.case_id,incoming.id,incoming.v,incoming.label,incoming.rev FROM `orchestrator10000`.`dbt_delta_boolean` AS incoming LEFT JOIN `orchestrator10000`.`dbt_boolean` AS original ON original.case_id=incoming.case_id AND original.id=incoming.id WHERE original.id IS NULL
    )

  
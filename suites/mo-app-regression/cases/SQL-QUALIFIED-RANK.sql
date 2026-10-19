CREATE TABLE rank_source (id INT PRIMARY KEY, `rank` SMALLINT UNSIGNED, global_rank VARCHAR(255));

CREATE TABLE rank_stage (id INT UNIQUE, `rank` SMALLINT UNSIGNED, global_rank VARCHAR(255));

INSERT INTO rank_source VALUES (1,1,'old'),(2,42,'unchanged 中文');

INSERT INTO rank_stage VALUES (1,9,'updated 中文');

SELECT t1.rank FROM rank_source t1 ORDER BY id;

UPDATE rank_source AS t1, rank_stage AS t2 SET t1.rank = t2.rank, t1.global_rank = t2.global_rank WHERE t1.id = t2.id;

SELECT id,`rank`,global_rank FROM rank_source ORDER BY id;

UPDATE rank_source AS t1, rank_stage AS t2 SET t1.`rank` = t2.`rank`, t1.global_rank = t2.global_rank WHERE t1.id = t2.id;

SELECT id,`rank`,global_rank FROM rank_source ORDER BY id;

SELECT 1;

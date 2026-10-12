-- SQL-FULLTEXT-INSERT-ID: FULLTEXT index corrupts session insert ID

-- Requires a fresh isolated database. No database is deleted.

-- @setup

CREATE TABLE id_probe(id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,label VARCHAR(40));

-- @setup

ALTER TABLE id_probe ADD FULLTEXT label_ft(label);

-- @setup

INSERT INTO id_probe(label) VALUES('small');

-- @trigger

SELECT id,LAST_INSERT_ID() FROM id_probe;

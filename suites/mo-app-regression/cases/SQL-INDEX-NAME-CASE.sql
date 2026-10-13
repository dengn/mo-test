-- SQL-INDEX-NAME-CASE: Index identifier case is folded

-- Requires a fresh isolated database. No database is deleted.

-- @setup

CREATE TABLE index_probe(id INT PRIMARY KEY);

-- @setup

CREATE INDEX IDX_mo_probe_test ON index_probe(id);

-- @trigger

SELECT INDEX_NAME FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='index_probe' AND INDEX_NAME<>'PRIMARY';

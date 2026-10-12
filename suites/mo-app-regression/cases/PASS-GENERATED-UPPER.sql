-- PASS-GENERATED-UPPER: Stored UPPER index, Unicode and NULL semantics

-- Requires a fresh isolated database. No database is deleted.

-- @setup

CREATE TABLE expr_probe(id INT PRIMARY KEY,email VARCHAR(254),email_upper VARCHAR(254) GENERATED ALWAYS AS (UPPER(email)) STORED);

-- @setup

CREATE INDEX idx_upper ON expr_probe(email_upper);

-- @setup

INSERT INTO expr_probe(id,email) VALUES(1,'MiXeD中文😀𠮷@owned.invalid'),(2,NULL);

-- @trigger

SELECT id,email_upper FROM expr_probe ORDER BY id;

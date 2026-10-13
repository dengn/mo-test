-- PASS-ROLLBACK: Explicit transaction rollback exact values

-- Requires a fresh isolated database. No database is deleted.

-- @setup

CREATE TABLE txn_probe(id INT PRIMARY KEY,value INT);

-- @setup

INSERT INTO txn_probe VALUES(1,17);

-- @setup

START TRANSACTION;

-- @setup

UPDATE txn_probe SET value=99 WHERE id=1;

-- @setup

ROLLBACK;

-- @trigger

SELECT id,value FROM txn_probe;

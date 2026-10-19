-- PASS-JSON-UNICODE: JSON and four byte Unicode values

-- Requires a fresh isolated database. No database is deleted.

-- @setup

CREATE TABLE values_probe(id INT PRIMARY KEY,payload JSON,label TEXT);

-- @setup

INSERT INTO values_probe VALUES(1,'{"value":"中文 😀𠮷"}','中文 😀𠮷');

-- @trigger

SELECT id,label,JSON_UNQUOTE(JSON_EXTRACT(payload,'$.value')) FROM values_probe;

-- Exact executable fixture is the JSON case; runner preserves each assertion.
CREATE TABLE doc_alias(id INT PRIMARY KEY,c_sub VARCHAR(200) NULL);
INSERT INTO doc_alias VALUES(1,'中文 😀𠮷'),(2,NULL);
SELECT id,c_sub AS subscription FROM doc_alias ORDER BY id;

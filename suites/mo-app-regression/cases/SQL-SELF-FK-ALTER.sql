-- SQL-SELF-FK-ALTER: Populated self FK VARCHAR ALTER

-- Requires a fresh isolated database. No database is deleted.

-- @setup

CREATE TABLE self_probe(id INT PRIMARY KEY,parent_id INT NULL,URL VARCHAR(100),CONSTRAINT fk_self FOREIGN KEY(parent_id) REFERENCES self_probe(id));

-- @setup

INSERT INTO self_probe VALUES(1,NULL,'parent'),(2,1,'child');

-- @trigger

ALTER TABLE self_probe MODIFY COLUMN URL VARCHAR(125);

-- @postcondition

SELECT id,parent_id,URL FROM self_probe ORDER BY id;

-- @postcondition

INSERT INTO self_probe VALUES(3,999,'must reject');

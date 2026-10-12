-- SQL-CHECK-DROP: DROP CHECK parser restriction

-- Requires a fresh isolated database. No database is deleted.

-- @setup

CREATE TABLE checks(id INT PRIMARY KEY,minimum INT,CONSTRAINT chk_minimum CHECK(minimum>=0));

-- @trigger

ALTER TABLE checks DROP CHECK chk_minimum;

-- @postcondition

INSERT INTO checks VALUES (1,-1);

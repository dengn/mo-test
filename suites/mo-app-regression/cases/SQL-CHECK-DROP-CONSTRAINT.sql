-- SQL-CHECK-DROP-CONSTRAINT: DROP CONSTRAINT cannot find CHECK

-- Requires a fresh isolated database. No database is deleted.

-- @setup

CREATE TABLE checks(id INT PRIMARY KEY,minimum INT,CONSTRAINT chk_minimum CHECK(minimum>=0));

-- @trigger

ALTER TABLE checks DROP CONSTRAINT chk_minimum;

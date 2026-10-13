-- SQL-JSON-DEFAULT: JSON default restriction

-- Requires a fresh isolated database. No database is deleted.

-- @trigger

CREATE TABLE json_default (id INT, payload JSON DEFAULT ('{}'));

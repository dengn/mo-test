-- SQL-COMBINED-FK: ADD COLUMN plus ADD FK restriction

-- Requires a fresh isolated database. No database is deleted.

-- @setup

CREATE TABLE parent(id INT PRIMARY KEY);

-- @setup

CREATE TABLE child(id INT PRIMARY KEY);

-- @trigger

ALTER TABLE child ADD COLUMN parent_id INT NULL, ADD CONSTRAINT combined_fk FOREIGN KEY(parent_id) REFERENCES parent(id);

-- PANIC-03: Unique LOWER expression index

-- Use an isolated database. This file does not choose or delete a database.

-- Original/reconstructed boundaries are documented in the adjacent JSON file.

-- @setup

CREATE TABLE mo_index_probe (id INT PRIMARY KEY, email VARCHAR(254));

-- @trigger

CREATE UNIQUE INDEX mo_unique_email_expression ON mo_index_probe ((LOWER(email)));

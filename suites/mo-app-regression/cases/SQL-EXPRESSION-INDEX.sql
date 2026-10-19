-- SQL-EXPRESSION-INDEX: Nonunique UPPER expression index

-- Requires a fresh isolated database. No database is deleted.

-- @setup

CREATE TABLE account_emailaddress(id INT PRIMARY KEY,email VARCHAR(254));

-- @trigger

CREATE INDEX account_email_upper ON account_emailaddress((UPPER(email)));

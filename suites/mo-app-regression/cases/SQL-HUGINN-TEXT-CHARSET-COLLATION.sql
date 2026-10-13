-- JSON fixture contains authoritative value/constraint assertions.
CREATE TABLE h_text(id INT PRIMARY KEY,options TEXT NULL);
INSERT INTO h_text VALUES(1,'AbC 中文 😀𠮷'),(2,'abc 中文 😀𠮷'),(3,NULL);
ALTER TABLE h_text CHANGE options options text CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL;

-- PANIC-01: Shiori Boolean fulltext single quote

-- Use an isolated database. This file does not choose or delete a database.

-- Original/reconstructed boundaries are documented in the adjacent JSON file.

-- @setup

CREATE TABLE `bookmark` (
  `id` int NOT NULL AUTO_INCREMENT,
  `url` text NOT NULL,
  `title` text NOT NULL,
  `excerpt` text NOT NULL DEFAULT (''),
  `author` text NOT NULL DEFAULT (''),
  `public` bool NOT NULL DEFAULT 0,
  `content` text NOT NULL DEFAULT (''),
  `html` text NOT NULL DEFAULT (''),
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP(),
  `has_content` bool NOT NULL DEFAULT 0,
  `modified_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP(),
  PRIMARY KEY (`id`),
  UNIQUE KEY `bookmark_url_unique` (`url`(255)),
 FULLTEXT (`title`,`excerpt`,`content`),
  KEY `idx_created_at` (`created_at`),
  KEY `idx_modified_at` (`modified_at`)
);

-- @setup

INSERT INTO bookmark (id,url,title,excerpt,content) VALUES (1,'https://owned.invalid/example','test title','test excerpt','test content');

-- @trigger

SELECT id,url,title,excerpt,author,public,created_at,modified_at,content <> "" AS has_content
FROM bookmark
WHERE 1 AND (
    url LIKE '%"%' OR
    id IN (SELECT id FROM bookmark
           WHERE MATCH(title, excerpt, content) AGAINST ('"' IN BOOLEAN MODE))
)
ORDER BY id;

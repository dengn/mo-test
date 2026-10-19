-- PANIC-04: Wagtail multiple FULLTEXT indexed INSERT

-- Use an isolated database. This file does not choose or delete a database.

-- Original/reconstructed boundaries are documented in the adjacent JSON file.

-- @setup

CREATE TABLE `django_content_type` (
  `id` int NOT NULL AUTO_INCREMENT,
  `app_label` varchar(100) NOT NULL,
  `model` varchar(100) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `django_content_type_app_label_model_76bd3d3b_uniq` (`app_label`,`model`)
);

-- @setup

INSERT INTO django_content_type VALUES (10002,'home','homepage');

-- @setup

CREATE TABLE `wagtailsearch_indexentry` (
  `id` int NOT NULL AUTO_INCREMENT,
  `object_id` varchar(50) NOT NULL,
  `title_norm` double NOT NULL,
  `content_type_id` int NOT NULL,
  `autocomplete` text DEFAULT NULL,
  `body` text DEFAULT NULL,
  `title` text NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `wagtailsearch_indexentry_content_type_id_object_id_bcd7ba73_uniq` (`content_type_id`,`object_id`),
  KEY `wagtailsearch_indexentry_content_type_id_62ed694f` (`content_type_id`),
 FULLTEXT `fulltext_body`(`body`),
 FULLTEXT `fulltext_title`(`title`),
 FULLTEXT `fulltext_title_body`(`title`,`body`),
 FULLTEXT `fulltext_autocomplete`(`autocomplete`),
  CONSTRAINT `wagtailsearch_indexe_content_type_id_62ed694f_fk_django_co` FOREIGN KEY (`content_type_id`) REFERENCES `django_content_type` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT
);

-- @trigger

INSERT INTO `wagtailsearch_indexentry` (`content_type_id`, `object_id`, `title_norm`, `autocomplete`, `title`, `body`) VALUES (10002, '40001', 1.0, 'Home', 'Home', '');

-- @trigger

SELECT content_type_id,object_id,title_norm,autocomplete,title,body FROM wagtailsearch_indexentry;

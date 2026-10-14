-- Captured native SQL on v4.2.5; use only a dedicated disposable instance.

-- Native transaction index INSERT panic matches PANIC-04 / MatrixOne #29899.

-- Schema is new; preserve existing databases.

CREATE DATABASE mo_wagtail_fulltext_capture_795cbbbeff31;

USE mo_wagtail_fulltext_capture_795cbbbeff31;

CREATE TABLE `django_content_type` (
  `id` int NOT NULL AUTO_INCREMENT,
  `app_label` varchar(100) NOT NULL,
  `model` varchar(100) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `django_content_type_app_label_model_76bd3d3b_uniq` (`app_label`,`model`)
);

INSERT INTO django_content_type (id,app_label,model) VALUES (10002,'home','homepage');

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

INSERT INTO `wagtailsearch_indexentry` (`content_type_id`, `object_id`, `title_norm`, `autocomplete`, `title`, `body`) VALUES (10002, '140002', 1.0e0, '原生草稿 中文 😀𠮷', '原生草稿 中文 😀𠮷', '');

SELECT 1;

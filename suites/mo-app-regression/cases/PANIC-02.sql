-- PANIC-02: Wagtail correlated UPDATE with CASE and JOIN

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

CREATE TABLE `auth_permission` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(255) NOT NULL,
  `content_type_id` int NOT NULL,
  `codename` varchar(100) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `auth_permission_content_type_id_codename_01ab375a_uniq` (`content_type_id`,`codename`),
  KEY `auth_permission_content_type_id_2f476e4b` (`content_type_id`),
  CONSTRAINT `auth_permission_content_type_id_2f476e4b_fk_django_co` FOREIGN KEY (`content_type_id`) REFERENCES `django_content_type` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT
);

-- @setup

CREATE TABLE wagtailcore_grouppagepermission (
 id INT PRIMARY KEY, permission_type VARCHAR(20) DEFAULT NULL,
 group_id INT NOT NULL, page_id INT NOT NULL, permission_id INT DEFAULT NULL,
 CONSTRAINT permission_fk FOREIGN KEY(permission_id) REFERENCES auth_permission(id)
);

-- @setup

INSERT INTO django_content_type VALUES (10001,'wagtailcore','page');

-- @setup

INSERT INTO auth_permission (id,name,content_type_id,codename) VALUES (101,'change page',10001,'change_page'),(102,'add page',10001,'add_page'),(103,'publish page',10001,'publish_page');

-- @setup

INSERT INTO wagtailcore_grouppagepermission VALUES (1,'edit',1,1,NULL),(2,'add',1,1,NULL),(3,'publish',1,1,NULL);

-- @trigger

UPDATE `wagtailcore_grouppagepermission` SET `permission_id` = (SELECT U0.`id` AS `pk` FROM `auth_permission` U0 INNER JOIN `django_content_type` U1 ON (U0.`content_type_id` = U1.`id`) WHERE (U0.`codename` = (CONCAT_WS('', CASE WHEN (`wagtailcore_grouppagepermission`.`permission_type` = 'edit') THEN 'change' ELSE `wagtailcore_grouppagepermission`.`permission_type` END, '_page')) AND U0.`content_type_id` = 10001) ORDER BY U1.`app_label` ASC, U1.`model` ASC, U0.`codename` ASC LIMIT 1), `permission_type` = CASE WHEN (`wagtailcore_grouppagepermission`.`permission_type` = 'edit') THEN 'change' ELSE `wagtailcore_grouppagepermission`.`permission_type` END WHERE (`wagtailcore_grouppagepermission`.`permission_id` IS NULL OR `wagtailcore_grouppagepermission`.`permission_type` = 'edit');

-- @trigger

SELECT id,permission_type,permission_id FROM wagtailcore_grouppagepermission ORDER BY id;

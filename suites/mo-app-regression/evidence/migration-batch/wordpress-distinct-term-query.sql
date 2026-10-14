-- Native default-post taxonomy lookup; reads only the dedicated new fixture schema.
SELECT DISTINCT t.term_id, tr.object_id
			 FROM wp_terms AS t  INNER JOIN wp_term_taxonomy AS tt ON t.term_id = tt.term_id INNER JOIN wp_term_relationships AS tr ON tr.term_taxonomy_id = tt.term_taxonomy_id
			 WHERE tt.taxonomy IN ('category', 'post_tag', 'post_format') AND tr.object_id IN (1)
			 ORDER BY t.name ASC;

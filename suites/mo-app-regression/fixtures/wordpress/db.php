<?php
/** MatrixOne compatibility for core WordPress queries; plugin coverage untested. */
class MatrixOne_WPDB extends wpdb {
    public function query($query) {
        // Core add_option assigns the unique key to its existing value. Remove
        // only that no-op assignment; keep the atomic non-key updates intact.
        if (str_contains($query, '`' . $this->options . '`') && stripos($query, 'ON DUPLICATE KEY UPDATE') !== false) {
            $query = preg_replace('/(ON DUPLICATE KEY UPDATE\s+)`option_name`\s*=\s*VALUES\(`option_name`\),\s*/i', '$1', $query);
        }
        // Core's expired-transient cleanup joins the mixed-type options table.
        // Avoid casting unrelated serialized option values to integers.
        if (str_contains($query, 'DELETE a, b FROM ' . $this->options) && str_contains($query, 'transient_timeout_')) {
            $query = preg_replace('/b\.option_value\s*<\s*([0-9]+)/', "CAST(CASE WHEN b.option_value REGEXP '^[0-9]+$' THEN b.option_value ELSE '0' END AS UNSIGNED) < $1", $query);
        }
        // term_id is a primary key: adding its term name preserves DISTINCT
        // cardinality while satisfying MatrixOne's ORDER BY select-list rule.
        if (preg_match('/ORDER BY\s+t\.name\s+ASC/i', $query)) {
            $query = preg_replace('/SELECT DISTINCT t\.term_id(?=\s*(?:,|FROM\b))/', 'SELECT DISTINCT t.term_id, t.name', $query);
        }
        $result = parent::query($query);
        // MatrixOne folds unaliased column metadata to lowercase. Preserve
        // lowercase values and add the core names WordPress expects.
        foreach ($this->last_result as $row) {
            foreach (['id' => 'ID', 'comment_id' => 'comment_ID', 'comment_post_id' => 'comment_post_ID'] as $lower => $canonical) {
                if (property_exists($row, $lower) && !property_exists($row, $canonical)) {
                    $row->$canonical = $row->$lower;
                }
            }
        }
        return $result;
    }
}
$wpdb = new MatrixOne_WPDB(DB_USER, DB_PASSWORD, DB_NAME, DB_HOST);

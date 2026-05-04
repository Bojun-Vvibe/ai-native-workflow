<?php
// Good: debug on with log enabled, display unset is fine because
// the operator opted into log-only mode.
define('WP_DEBUG', true);
define('WP_DEBUG_LOG', true);
define('DB_NAME', 'site');
$table_prefix = 'wp_';

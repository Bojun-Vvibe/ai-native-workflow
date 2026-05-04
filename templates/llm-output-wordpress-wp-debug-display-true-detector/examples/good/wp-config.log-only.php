<?php
// Good: debug on but display explicitly off, and log on.
define('WP_DEBUG', true);
define('WP_DEBUG_DISPLAY', false);
define('WP_DEBUG_LOG', true);
@ini_set('display_errors', 0);
define('DB_NAME', 'site');
$table_prefix = 'wp_';

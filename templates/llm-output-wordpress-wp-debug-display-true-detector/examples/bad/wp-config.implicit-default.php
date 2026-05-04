<?php
// Bad: WP_DEBUG=true and WP_DEBUG_DISPLAY unset -> defaults to on.
// No WP_DEBUG_LOG override either, so errors render to clients.
define('WP_DEBUG', true);
define('DB_NAME', 'site');
define('DB_USER', 'site');
define('DB_PASSWORD', 'changeme');
define('DB_HOST', '127.0.0.1');
$table_prefix = 'wp_';

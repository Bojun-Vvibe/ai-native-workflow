<?php
// Bad: explicit WP_DEBUG_DISPLAY=true with WP_DEBUG on.
define('WP_DEBUG', true);
define('WP_DEBUG_DISPLAY', true);
define('DB_NAME', 'wordpress');
define('DB_USER', 'wp');
define('DB_HOST', 'localhost');
$table_prefix = 'wp_';

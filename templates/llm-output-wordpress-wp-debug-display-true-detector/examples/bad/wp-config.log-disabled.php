<?php
// Bad: WP_DEBUG_LOG=false explicitly disables the log too, and
// WP_DEBUG_DISPLAY is unset so it defaults to on.
define('WP_DEBUG', true);
define('WP_DEBUG_LOG', false);
define('DB_NAME', 'shop');
$table_prefix = 'wp_';

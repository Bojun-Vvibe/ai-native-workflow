<?php
// Errors go to stderr (captured by container log driver), not the response body.
ini_set('display_errors', 'stderr');
ini_set('log_errors', '1');
error_reporting(E_ALL);

require __DIR__ . '/vendor/autoload.php';

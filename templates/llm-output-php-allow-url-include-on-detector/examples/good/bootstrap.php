<?php
// bootstrap.php — never enables url include
ini_set('allow_url_include', '0');
ini_set('display_errors', '0');

$module = basename($_GET['module'] ?? 'home');
require __DIR__ . '/modules/' . $module . '.php';

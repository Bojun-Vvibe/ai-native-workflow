<?php
// Safe fixtures. Detector must NOT flag any line in this file.

// Static include — no taint.
include __DIR__ . "/pages/home.php";

// basename() mitigation present.
$page = $_GET['page'];
include basename($page) . ".php";

// in_array allowlist mitigation present.
$p = $_REQUEST['p'];
$allowed = ['home', 'about', 'contact'];
if (in_array($p, $allowed, true)) {
    include "pages/" . $p . ".php";
}

// realpath() mitigation present.
require realpath(__DIR__ . "/" . $_GET['tpl']);

// preg_match() inline mitigation present.
$mod = $_GET['mod'];
require_once preg_match('/^[a-z]+$/', $mod) ? "modules/$mod.php" : "modules/default.php";

// array_key_exists inline mitigation present.
$routes = ['home' => 'home.php', 'about' => 'about.php'];
include array_key_exists($_GET['r'], $routes) ? "pages/" . $routes[$_GET['r']] : "pages/404.php";

// Suppressed line via allow-marker (rare audited case).
include $_GET['legacy_page']; // llm-allow:php-include-tainted

// Comment containing fake include — must not fire.
// include $_GET['x'];

// String literal mentioning $_GET — must not fire.
$msg = "Avoid include \$_GET['page'];";
echo $msg;
?>

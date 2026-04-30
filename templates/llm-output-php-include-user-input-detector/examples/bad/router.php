<?php
// Fixtures for the LFI-shape detector. These are intentionally
// vulnerable patterns the detector must flag. They are NOT exploits —
// they reference no payloads and contain no traversal strings.

// Finding 1: bare include of $_GET.
include $_GET['page'];

// Finding 2: include_once with concat trailing ".php" (still tainted).
include_once "pages/" . $_REQUEST['p'] . ".php";

// Finding 3: require with __DIR__ prefix.
require __DIR__ . "/" . $_GET['tpl'];

// Finding 4: require_once call form with $_POST.
require_once($_POST['mod']);

// Finding 5: include from $_COOKIE.
include $_COOKIE['theme'] . ".inc.php";

// Finding 6: require with $_SERVER['PATH_INFO'] (also tainted).
require "modules/" . $_SERVER['PATH_INFO'];

// Finding 7: include_once call form with $_FILES.
include_once($_FILES['upload']['name']);
?>

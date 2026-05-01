<?php
// Bad samples for php-file-read-traversal detector.
// All 8 lines below should each yield exactly one finding.

// 1. php-file-get-contents-tainted: bare $_GET superglobal
$body = file_get_contents($_GET['path']);

// 2. php-file-get-contents-tainted: concatenation with $_POST
$data = file_get_contents("/var/data/" . $_POST['name']);

// 3. php-file-get-contents-tainted: $_REQUEST inside expression
$blob = file_get_contents($_REQUEST['file'] . ".json");

// 4. php-readfile-tainted: readfile of $_GET param
readfile($_GET['file']);

// 5. php-fopen-tainted: fopen with $_COOKIE
$h = fopen($_COOKIE['session_log'], 'r');

// 6. php-file-tainted: file() reading user-supplied path into array
$lines = file($_GET['log']);

// 7. php-file-get-contents-tainted: filter_input helper (still tainted)
$body2 = file_get_contents(filter_input(INPUT_GET, 'p'));

// 8. php-readfile-tainted: $_SERVER value used as path
readfile($_SERVER['HTTP_X_TARGET']);

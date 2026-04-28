<?php
// 01_user_formula.php — accepts arbitrary expressions over HTTP.
$expr = $_GET['formula'] ?? '1+1';
$result = null;
eval('$result = ' . $expr . ';');
echo $result;

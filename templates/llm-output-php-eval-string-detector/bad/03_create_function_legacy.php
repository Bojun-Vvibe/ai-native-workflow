<?php
// 03_create_function_legacy.php
$cmp = create_function('$a, $b', 'return strlen($a) - strlen($b);');
usort($items, $cmp);

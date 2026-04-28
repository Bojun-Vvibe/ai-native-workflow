<?php
// 03_comments_and_strings.php — mentions in comments/strings only.
// We deliberately do NOT use eval() here.
# Another reminder: never call eval(...) on user input.
/*
 * Historical note: create_function() was removed.
 * Some legacy code used assert('...') as a poor-man's eval.
 */
$msg = "Do not call eval(...) here.";
$tip = 'create_function( was deprecated';
echo $msg . $tip;

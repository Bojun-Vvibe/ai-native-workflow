<?php
// 04_assert_string.php — pre-PHP 8 assert($string) evaluates as code.
function check($value) {
    assert('$value > 0 && $value < 100');
}

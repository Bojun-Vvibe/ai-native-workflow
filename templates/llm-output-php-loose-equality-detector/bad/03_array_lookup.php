<?php

function find_user($users, $needle) {
    foreach ($users as $u) {
        if ($u["id"] == $needle) {  // BAD: "1" == 1 == true
            return $u;
        }
    }
    return null;
}

function is_zero($x) {
    return $x == 0;  // BAD: any non-numeric string equals 0 on PHP 7
}

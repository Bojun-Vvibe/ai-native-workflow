<?php
// Classic loose-equality foot-gun: 0 == "anything-not-numeric" was true on PHP < 8.

function is_admin($role) {
    if ($role == "admin") {  // should be ===
        return true;
    }
    return false;
}

function password_matches($a, $b) {
    return $a == $b;  // should be ===, ideally hash_equals()
}

$status = "0";
if ($status != false) {  // should be !==; "0" == false is true!
    echo "active\n";
}

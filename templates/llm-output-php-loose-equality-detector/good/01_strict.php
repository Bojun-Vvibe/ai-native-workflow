<?php
// All comparisons use strict ===/!==. Comments and strings that contain
// "==" must NOT trigger.

function is_admin(string $role): bool {
    // historically people wrote: if ($role == "admin") { ... } — but we use ===.
    return $role === "admin";
}

function token_matches(string $a, string $b): bool {
    // hash_equals avoids timing attacks; === is fine for non-secret strings.
    return hash_equals($a, $b);
}

function status_active(string $status): bool {
    return $status !== "0" && $status !== "";
}

$marker = "==>"; // arrow-like marker in a string, must not trigger
$banner = "use === not == in PHP";  // explanatory string, must not trigger
echo $marker, $banner, "\n";

<?php

$debug = getenv("DEBUG");

// BAD: loose != means "0", "false", "" all collapse to falsy in unexpected ways
if ($debug != "true") {
    error_reporting(E_ALL);
}

// BAD: <> spelled-out form
if ($_SERVER["REQUEST_METHOD"] <> "POST") {
    http_response_code(405);
    exit;
}

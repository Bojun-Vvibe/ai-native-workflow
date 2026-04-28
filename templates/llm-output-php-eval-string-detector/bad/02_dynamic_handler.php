<?php
// 02_dynamic_handler.php
function dispatch($name, $payload) {
    $code = "return handle_" . $name . "(\$payload);";
    return eval($code);
}

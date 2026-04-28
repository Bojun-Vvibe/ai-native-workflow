<?php
// 01_safe_dispatch.php — whitelist dispatch instead of eval.
$handlers = [
    'add' => fn($a, $b) => $a + $b,
    'mul' => fn($a, $b) => $a * $b,
];
$op = $_GET['op'] ?? 'add';
if (!isset($handlers[$op])) {
    http_response_code(400);
    exit;
}
echo $handlers[$op](2, 3);

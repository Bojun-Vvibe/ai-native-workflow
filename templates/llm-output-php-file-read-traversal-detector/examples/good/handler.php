<?php
// Good samples for php-file-read-traversal detector.
// None of these should produce a finding.

// Safe: fully literal path.
$banner = file_get_contents('/etc/hostname');

// Safe: literal under __DIR__.
$tpl = file_get_contents(__DIR__ . '/templates/header.html');

// Safe: literal-only readfile.
readfile('/var/www/static/robots.txt');

// Safe: fopen with literal name.
$h = fopen('/tmp/build.log', 'a');

// Safe: file() with literal path.
$lines = file('/etc/hosts');

// Safe: realpath()-wrapped argument (audited shape).
function read_safely(string $name): string {
    $base = realpath('/srv/data');
    $candidate = $base . '/' . basename($name);
    $real = realpath($candidate);
    if ($real === false || strncmp($real, $base . '/', strlen($base) + 1) !== 0) {
        http_response_code(400);
        exit;
    }
    return file_get_contents($real);
}

// Safe: inline realpath() wrapping (single-call shape) — also audited.
$audited = file_get_contents(realpath('/srv/data/banner.txt'));

// Safe: comment that mentions file_get_contents($_GET['x']) — comment-stripped.
// This line: file_get_contents($_GET['x']); should NOT trigger.

// Safe: a method on a user class is not the global function.
class Loader {
    public function file_get_contents(string $k): string { return ''; }
}
$loader = new Loader();
$x = $loader->file_get_contents($_GET['k']);

// Safe: explicitly audited (suppression marker).
$body = file_get_contents($_GET['p']); // llm-allow:php-path-traversal

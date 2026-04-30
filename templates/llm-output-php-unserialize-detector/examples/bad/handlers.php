<?php
// Bad fixtures: every unserialize() here MUST be flagged by detect.py.

// 1. Direct superglobal.
$session = unserialize($_GET['session']);

// 2. POST body.
$prefs = unserialize($_POST['prefs']);

// 3. Cookie.
$auth = unserialize($_COOKIE['auth']);

// 4. Raw HTTP body via the canonical PHP idiom.
$payload = file_get_contents('php://input');
$obj = unserialize($payload);

// 5. file_get_contents directly inline.
$cfg = unserialize(file_get_contents('php://input'));

// 6. Untrusted-named variable assigned from a request.
$user_blob = $_REQUEST['blob'];
$user_obj = unserialize($user_blob);

// 7. base64-decoded request data — common obfuscation.
$evil = unserialize(base64_decode($_GET['data']));

// 8. gz-uncompressed body.
$z = unserialize(gzuncompress(file_get_contents('php://input')));

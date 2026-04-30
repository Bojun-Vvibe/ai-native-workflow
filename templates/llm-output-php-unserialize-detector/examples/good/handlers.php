<?php
// Good fixtures: nothing here should be flagged.

// 1. JSON instead of unserialize — the safe alternative for
// request-shaped data.
$prefs = json_decode($_POST['prefs'], true);

// 2. unserialize on a known-safe constant.
$default_state = unserialize('a:0:{}');

// 3. unserialize on a value pulled from the local filesystem under
// our own control. The variable name does not match any of the
// untrusted prefixes, and the source is not a superglobal.
$cached_blob = file_get_contents(__DIR__ . '/cache/snapshot.bin');
$snapshot = unserialize($cached_blob, ['allowed_classes' => false]);

// 4. Reading a request body but explicitly opting in to JSON, never
// invoking unserialize at all.
$body = file_get_contents('php://input');
$decoded = json_decode($body, true);

// 5. Suppressed line — author has signed off and we trust the source.
$blob_from_internal_queue = stream_get_contents($queue_handle);
$msg = unserialize($blob_from_internal_queue); // not flagged: name not untrusted

// 6. Comment that mentions unserialize($_GET['x']) should NOT trip
// the detector — comments are blanked.

/*
 * Block comment example: unserialize($_POST['evil']);
 */

// 7. Suppression marker on an obviously-untrusted call (covers the
// "I know what I'm doing" path).
$opt_in = unserialize($_GET['session']); // llm-allow:php-unserialize

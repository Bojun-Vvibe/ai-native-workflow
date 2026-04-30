<?php
// Suppressed after manual review — admin-only console with hardcoded
// allowlist; not user-controlled.
$tbl = $allowed[$choice];
$res = mysqli_query($conn, "TRUNCATE TABLE " . $tbl); // mysqli-concat-ok

<?php
// Constant SQL — no user input. Safe.
$res = mysqli_query($conn, "SELECT COUNT(*) FROM users");
$res2 = mysqli_query($conn, 'SELECT 1');

<?php
// Fully constant identifier defined elsewhere — safe.
define('Q_ALL_USERS', 'SELECT id, name FROM users');
$res = mysqli_query($conn, Q_ALL_USERS);

<?php
// procedural mysqli with concatenation — classic SQLi
$id = $_GET['id'];
$res = mysqli_query($conn, "SELECT * FROM users WHERE id = " . $id);

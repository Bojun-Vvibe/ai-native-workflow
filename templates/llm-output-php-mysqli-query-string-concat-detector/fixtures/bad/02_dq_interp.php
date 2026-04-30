<?php
// double-quoted interpolation
$name = $_POST['name'];
$res = mysqli_query($conn, "SELECT * FROM users WHERE name = '$name'");

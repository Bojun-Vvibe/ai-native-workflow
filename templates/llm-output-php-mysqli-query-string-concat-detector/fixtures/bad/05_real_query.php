<?php
// real_query procedural, sql built upstream as bare $sql variable
$sql = "DELETE FROM logs WHERE id=" . intval($_GET['id']);
mysqli_real_query($conn, $sql);

<?php
// multi_query is even worse — stacked queries
$role = $_GET['role'];
$db->multi_query("SELECT * FROM users WHERE role='" . $role . "'; SELECT 1;");

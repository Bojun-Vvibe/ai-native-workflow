<?php
// bootstrap.php
ini_set('allow_url_include', '1');
ini_set('allow_url_fopen', '1');

require $_GET['module'] . '.php';

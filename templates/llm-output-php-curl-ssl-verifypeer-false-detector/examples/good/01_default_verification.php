<?php
// Default behavior: verification stays on. Don't touch the option.
$ch = curl_init('https://api.example.com/v1/ping');
curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
curl_setopt($ch, CURLOPT_TIMEOUT, 10);
$out = curl_exec($ch);
curl_close($ch);

<?php
$ch = curl_init();
curl_setopt_array($ch, [
    CURLOPT_URL => 'https://api.example.com/data',
    CURLOPT_RETURNTRANSFER => true,
    CURLOPT_SSL_VERIFYPEER => false,
    CURLOPT_SSL_VERIFYHOST => 0,
]);
$body = curl_exec($ch);

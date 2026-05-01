<?php
$ch = curl_init();
curl_setopt_array($ch, [
    CURLOPT_URL            => 'https://api.example.com/data',
    CURLOPT_RETURNTRANSFER => true,
    CURLOPT_SSL_VERIFYPEER => true,
    CURLOPT_SSL_VERIFYHOST => 2,
    CURLOPT_CAINFO         => '/etc/ssl/certs/ca-bundle.crt',
]);
$body = curl_exec($ch);

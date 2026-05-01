<?php
$ch = curl_init();
curl_setopt($ch, CURLOPT_URL, 'https://api.example.com/v1');
curl_setopt($ch, CURLOPT_SSL_VERIFYPEER, "0");
$resp = curl_exec($ch);
curl_close($ch);

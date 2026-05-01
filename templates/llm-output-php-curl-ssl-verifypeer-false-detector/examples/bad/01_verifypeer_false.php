<?php
$ch = curl_init('https://api.example.com/v1/ping');
curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
curl_setopt($ch, CURLOPT_SSL_VERIFYPEER, false);
$out = curl_exec($ch);
curl_close($ch);

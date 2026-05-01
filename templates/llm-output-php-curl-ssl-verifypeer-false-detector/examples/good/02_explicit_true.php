<?php
// Explicitly leave verification on.
$ch = curl_init($url);
curl_setopt($ch, CURLOPT_SSL_VERIFYPEER, true);
curl_setopt($ch, CURLOPT_SSL_VERIFYHOST, 2);
curl_setopt($ch, CURLOPT_CAINFO, '/etc/ssl/certs/ca-bundle.crt');
$resp = curl_exec($ch);

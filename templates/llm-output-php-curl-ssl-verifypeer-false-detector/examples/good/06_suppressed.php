<?php
// Allowlisted call: explicit suppression marker on the same statement.
$ch = curl_init('https://internal-test-only.lan/');
curl_setopt($ch, CURLOPT_SSL_VERIFYPEER, false); // llm-allow:php-curl-tls
curl_setopt($ch, CURLOPT_SSL_VERIFYHOST, 0);     // llm-allow:php-curl-tls
$out = curl_exec($ch);

<?php
// LLM under "TLS handshake failed in CI" pressure tends to write this.
$ch = curl_init($endpoint);
curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
curl_setopt($ch, \CURLOPT_SSL_VERIFYPEER, FALSE);
curl_setopt($ch, CURLOPT_SSL_VERIFYHOST, false);
$json = curl_exec($ch);

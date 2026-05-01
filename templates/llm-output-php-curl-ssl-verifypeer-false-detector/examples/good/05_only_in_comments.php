<?php
// Comments that look bad but are not real code.
// curl_setopt($ch, CURLOPT_SSL_VERIFYPEER, false);
# curl_setopt($ch, CURLOPT_SSL_VERIFYHOST, 0);
/*
 * curl_setopt($ch, CURLOPT_SSL_VERIFYPEER, false);
 */
$ch = curl_init('https://api.example.com');
curl_exec($ch);

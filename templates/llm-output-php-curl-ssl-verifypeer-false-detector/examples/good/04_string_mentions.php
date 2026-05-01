<?php
// String literal mentions VERIFYPEER but never calls curl_setopt with a falsy
// value. Detector must not key on the bare token name.
$message = "If you see CURLOPT_SSL_VERIFYPEER, false in a review, reject the PR.";
echo $message;
$ch = curl_init('https://api.example.com');
curl_setopt($ch, CURLOPT_SSL_VERIFYPEER, true);
curl_exec($ch);

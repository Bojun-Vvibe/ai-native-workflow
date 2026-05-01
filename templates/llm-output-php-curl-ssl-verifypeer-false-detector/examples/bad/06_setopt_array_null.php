<?php
function fetch_legacy_endpoint(string $url): string {
    $ch = curl_init($url);
    curl_setopt_array($ch, [
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_SSL_VERIFYPEER => null,
        CURLOPT_TIMEOUT        => 10,
    ]);
    $out = curl_exec($ch);
    curl_close($ch);
    return $out ?: '';
}

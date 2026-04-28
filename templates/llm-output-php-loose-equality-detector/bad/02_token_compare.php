<?php

class TokenChecker {
    public function verify($expected, $given) {
        // BAD: loose comparison on a security-sensitive value
        if ($expected == $given) {
            return true;
        }
        return false;
    }

    public function legacy_compare($a, $b) {
        // BAD: <> is the same as !=
        return $a <> $b;
    }
}

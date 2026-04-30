<?php
// OO style, ->query with curly interpolation
class Repo {
    public function find(\mysqli $db, $email) {
        return $db->query("SELECT id FROM users WHERE email = '{$email}'");
    }
}

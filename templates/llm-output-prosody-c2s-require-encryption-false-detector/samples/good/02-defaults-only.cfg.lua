-- prosody.cfg.lua — good: defaults left alone (modern Prosody defaults to
-- requiring c2s + s2s encryption, so omitting the toggles is safe)
admins = { "admin@example.org" }
modules_enabled = { "roster"; "saslauth"; "tls"; "dialback" }

allow_registration = false

VirtualHost "example.org"
    enabled = true

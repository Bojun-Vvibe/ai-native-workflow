-- prosody.cfg.lua — bad: c2s_require_encryption explicitly off
admins = { "admin@example.org" }
modules_enabled = { "roster"; "saslauth"; "tls"; "dialback" }

c2s_require_encryption = false
allow_registration = false

VirtualHost "example.org"
    enabled = true

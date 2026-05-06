-- prosody.cfg.lua — good: encryption required on both channels
admins = { "admin@example.org" }
modules_enabled = { "roster"; "saslauth"; "tls"; "dialback" }

c2s_require_encryption = true
s2s_require_encryption = true
s2s_secure_auth = true

VirtualHost "example.org"
    enabled = true

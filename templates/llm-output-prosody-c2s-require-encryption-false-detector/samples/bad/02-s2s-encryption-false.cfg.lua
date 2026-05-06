-- prosody.cfg.lua — bad: s2s federation in plaintext, no secure_auth override
admins = { "ops@example.org" }
modules_enabled = { "roster"; "saslauth"; "tls"; "dialback" }

c2s_require_encryption = true
s2s_require_encryption = false
-- (no s2s_secure_auth set => federation runs in plaintext)

VirtualHost "example.org"
    enabled = true

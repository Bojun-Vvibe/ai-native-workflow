-- prosody.cfg.lua — good: s2s_require_encryption is false BUT
-- s2s_secure_auth = true forces certificate-validated TLS for every
-- federated peer, so the channel is still encrypted.
admins = { "admin@example.org" }
modules_enabled = { "roster"; "saslauth"; "tls"; "dialback" }

c2s_require_encryption = true
s2s_require_encryption = false
s2s_secure_auth = true

VirtualHost "example.org"
    enabled = true

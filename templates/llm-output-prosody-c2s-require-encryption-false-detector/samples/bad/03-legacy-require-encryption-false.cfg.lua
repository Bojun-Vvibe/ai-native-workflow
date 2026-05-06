-- prosody.cfg.lua — bad: legacy single-knob disable
-- (pre-0.10 style; still parsed by modern Prosody and downgrades both channels)
admins = { "admin@example.org" }
modules_enabled = { "roster"; "saslauth"; "dialback" }

require_encryption = false

VirtualHost "example.org"
    enabled = true

# llm-output-prosody-c2s-require-encryption-false-detector

Detect Prosody XMPP server configurations that LLMs commonly emit
with the encryption-required toggles explicitly turned off. Prosody
is a Lua-configured XMPP server. The `c2s_require_encryption`
option enforces TLS on the client-to-server channel — the channel
that carries the user's password during the SASL PLAIN handshake.
Turning it off downgrades every login on the server to plaintext on
the wire. The `s2s_require_encryption` twin governs server-to-server
federation; turning it off (without the stricter `s2s_secure_auth`
fallback) leaks every federated message between servers.

When asked "give me a Prosody config" or "make Prosody work without
TLS for local dev", models routinely:

- Emit `c2s_require_encryption = false` because they remember the
  knob exists and assume the user wants the simplest possible boot.
- Emit `s2s_require_encryption = false` "to avoid certificate
  errors" without also setting `s2s_secure_auth = true`, which is
  the only safe way to opt out of the require-encryption check.
- Reach for the legacy pre-0.10 single knob `require_encryption =
  false` (still parsed by modern Prosody, downgrades both channels).
- Render Docker / systemd env files with
  `PROSODY_C2S_REQUIRE_ENCRYPTION=false` (or the s2s twin) without
  any countervailing override.

## Bad patterns

1. Prosody Lua config with `c2s_require_encryption = false`.
2. Prosody Lua config with `s2s_require_encryption = false` AND
   no `s2s_secure_auth = true` override.
3. Prosody Lua config with the legacy `require_encryption = false`
   knob and no per-channel `*_require_encryption = true` override.
4. Docker / systemd / `.env` exporting
   `PROSODY_C2S_REQUIRE_ENCRYPTION=false` (or
   `PROSODY_S2S_REQUIRE_ENCRYPTION=false`).

## Good patterns

- `c2s_require_encryption = true` and `s2s_require_encryption =
  true` (explicit and modern).
- All encryption knobs absent (modern Prosody defaults to requiring
  encryption on both channels).
- `s2s_require_encryption = false` paired with `s2s_secure_auth =
  true`, which forces certificate-validated TLS on federation
  through a different code path.
- Docker env that sets both `PROSODY_C2S_REQUIRE_ENCRYPTION=true`
  and `PROSODY_S2S_REQUIRE_ENCRYPTION=true`.

## Tests

```sh
./detect.sh samples/bad/* samples/good/*
```

Verified-runnable smoke output (verbatim):

```
BAD  samples/bad/01-c2s-encryption-false.cfg.lua
BAD  samples/bad/02-s2s-encryption-false.cfg.lua
BAD  samples/bad/03-legacy-require-encryption-false.cfg.lua
BAD  samples/bad/04-env-c2s-false.env.txt
GOOD samples/good/01-c2s-and-s2s-required.cfg.lua
GOOD samples/good/02-defaults-only.cfg.lua
GOOD samples/good/03-s2s-secure-auth-override.cfg.lua
GOOD samples/good/04-env-encryption-required.env.txt
bad=4/4 good=0/4 PASS
```

## Why this matters

XMPP is one of the few protocols where SASL PLAIN over an unencrypted
transport is still common because the spec permits it. The whole
point of `c2s_require_encryption` is to refuse that combination at
the server. When an LLM disables the knob to "make local dev easier",
the resulting config silently becomes acceptable to staging /
production deploy pipelines, and every user's password traverses the
network in cleartext on the next reload. The s2s variant has the same
shape: federation traffic — including private messages and roster
pushes — flows in plaintext between servers.

The detector is deliberately narrow:

- It only fires on the explicit `false` form (or the env-var
  equivalent). It does not fire on configs that omit the knob,
  because modern Prosody defaults to requiring encryption.
- It accepts `s2s_secure_auth = true` as a safe alternative to
  `s2s_require_encryption = true`, matching the real Prosody
  semantics rather than a textual rule.
- It strips Lua line comments (`-- ...`) and shell `#` comments so
  that "documentation that mentions the bad pattern" doesn't
  false-fire.

Bash 3.2+ / coreutils only. No network calls.

# llm-output-coturn-no-auth-detector

Detect coturn (`turnserver`) configurations that LLMs commonly emit
with authentication disabled. coturn relays arbitrary UDP/TCP from
clients out through the server's network interface; without auth it
is an open relay — abusable for anonymising attack traffic, NAT-punch
reflection, bandwidth theft, and as a pivot into private networks
reachable from the coturn host.

When asked "set up a TURN server" or "give me a `turnserver.conf`",
models routinely:

- Drop in `no-auth` "to make WebRTC just work".
- Pass `--no-auth` on the `turnserver` CLI for the same reason.
- Wire `use-auth-secret` to the placeholder `static-auth-secret`
  value that ships in the upstream sample (`changeme`, `secret`,
  `coturn`, `please_change_me`, etc.).

## Bad patterns

1. `turnserver.conf` with an uncommented `no-auth` line.
2. CLI: `turnserver ... --no-auth ...` (note: `--no-auth-pings` is
   not the same flag and is not flagged).
3. `turnserver.conf` with `use-auth-secret` enabled AND
   `static-auth-secret=` set to a known placeholder, or missing
   entirely.

## Good patterns

- Configs with `lt-cred-mech` and a real `static-auth-secret`.
- Configs that comment out `no-auth` (commented lines are stripped
  before evaluation).
- CLI invocations that do not include `--no-auth`.

## Tests

```sh
./detect.sh samples/bad/* samples/good/*
```

Exit 0 iff every bad sample is flagged AND no good sample is.

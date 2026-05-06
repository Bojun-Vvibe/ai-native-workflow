# llm-output-vernemq-allow-anonymous-on-detector

Detect VerneMQ `vernemq.conf` snippets that LLMs commonly emit
with `allow_anonymous = on`. VerneMQ is an Erlang/OTP MQTT
broker; with anonymous access enabled, any TCP client that can
reach the listener can publish/subscribe to any topic without
presenting credentials and without going through the auth
chain. On the default listener (`0.0.0.0:1883`) this is an open
MQTT broker reachable from anywhere the listener IP is routable.

When asked "give me a vernemq.conf for testing" or "make my
MQTT broker accept clients without a password", models
routinely:

- Emit `allow_anonymous = on` because that's what the
  upstream "quickstart" docs show.
- Emit `allow_anonymous = true` / `yes` / `1` because they
  default to YAML/JSON-shaped booleans even though VerneMQ
  uses `on` / `off`.
- Pair the anonymous listener with `listener.tcp.default =
  0.0.0.0:1883`, exposing it to the whole interface.

## Bad patterns

1. `allow_anonymous = on`
2. `allow_anonymous = true`
3. `allow_anonymous = yes`
4. `allow_anonymous = 1`

## Good patterns

- `allow_anonymous = off` (or `false` / `no` / `0`).
- A VerneMQ-shaped config with no `allow_anonymous` line at
  all (default is `off`).
- A VerneMQ-shaped config that mentions `allow_anonymous = on`
  only inside `#` line comments.
- A non-VerneMQ file (no listener / plugin fingerprints) that
  happens to contain `allow_anonymous = on` for some unrelated
  tool — the detector requires a VerneMQ fingerprint.

## Tests

```sh
./detect.sh samples/bad/* samples/good/*
```

Verified-runnable smoke output (verbatim):

```
BAD  samples/bad/01-anon-on.conf
BAD  samples/bad/02-anon-true.conf
BAD  samples/bad/03-anon-yes.conf
BAD  samples/bad/04-anon-1.conf
GOOD samples/good/01-anon-off.conf
GOOD samples/good/02-anon-false.conf
GOOD samples/good/03-no-anon-line.conf
GOOD samples/good/04-comment-only.conf
bad=4/4 good=0/4 PASS
```

## Why this matters

MQTT brokers are commonly placed at the edge of an IoT or
telemetry network. With `allow_anonymous = on`:

- Any client that can reach the broker can `SUBSCRIBE #` and
  receive every message published on every topic — typically
  device telemetry, location data, command-and-control
  payloads.
- Any client can `PUBLISH` to any topic, including topics that
  devices treat as actuator commands (relay open/close, motor
  speed, dose-rate setpoints, garage-door triggers).
- The ACL plugin (`vmq_acl`) is bypassed in the anonymous
  path on older VerneMQ versions and depends on default-deny
  ACL files being authored correctly on newer ones; the safe
  default is to never let anonymous traffic into the
  publish/subscribe loop in the first place.

VerneMQ ships with `allow_anonymous = off` as the default and
the docs explicitly call out that turning it on is "for
development only". LLMs reproduce the development config
because that's the dominant shape in tutorials.

The detector is deliberately narrow:

- Requires at least one VerneMQ-shaped fingerprint
  (`listener.tcp.*`, `listener.ssl.*`, `plugins.vmq_*`,
  `vmq_acl.*`, `vmq_passwd.*`, etc.) so generic env files
  don't fire.
- Strips `#` comments before scanning, so commented-out
  examples in templates do not false-fire.
- Treats `on` / `true` / `yes` / `1` (case-insensitive) as
  truthy for `allow_anonymous`, matching what LLMs actually
  emit even though VerneMQ only documents `on` / `off`.
- A file with no `allow_anonymous` line at all does not fire,
  because the VerneMQ default is safe.

Bash 3.2+ / awk / coreutils only. No network calls.

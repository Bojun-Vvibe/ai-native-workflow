# llm-output-mqtt-broker-anonymous-allowed-detector

Static lint that flags MQTT broker configurations (mosquitto.conf,
docker-compose envs, HiveMQ snippets) that permit anonymous client
connections to a non-loopback listener.

`allow_anonymous true` plus a public listener means anyone who can
reach port 1883/8883 can subscribe to `#` and pump arbitrary payloads.
For an MQTT broker that fronts IoT devices or a pub/sub bus, this is
indistinguishable from no auth at all. LLMs asked "give me a working
mosquitto config" or "set up an MQTT broker in docker-compose"
default to this shape because it is what gets the broker to *start*
on first try.

## Why LLMs emit this

* Mosquitto pre-2.0 defaulted to `allow_anonymous true`, and that
  shape dominates pre-2020 training data — Stack Overflow, blog
  posts, hobbyist tutorials.
* Docker images like `eclipse-mosquitto:1.6` would silently accept
  anonymous connections; example compose files reflected that.
* Test scaffolds (`mosquitto_pub -h ... -t test -m hi`) work
  immediately with anonymous, so people copy-paste the working
  config into prod.

## What it catches

Per file (line-level):

- `allow_anonymous true` (mosquitto.conf style)
- `anonymous yes` (alternative-broker style)
- `MOSQUITTO_ALLOW_ANONYMOUS=true` / `MQTT_ALLOW_ANONYMOUS=true` /
  `HIVEMQ_ALLOW_ANONYMOUS=true` env-var assignments (compose / .env
  shape; quoted or unquoted)

Per file (whole-file):

- A non-loopback `listener` directive AND no
  `password_file` / `psk_file` / `auth_plugin` /
  `require_certificate true` directive AND no
  `allow_anonymous false` directive

## What it does NOT flag

- `allow_anonymous false` — explicit deny.
- `listener 1883 127.0.0.1` with no auth — loopback only is fine for
  dev.
- Lines with a trailing `# mqtt-anon-ok` comment.
- Files containing `# mqtt-anon-ok-file` anywhere.
- Blocks bracketed by `# mqtt-anon-ok-begin` / `# mqtt-anon-ok-end`.

## How to detect (the pattern)

Run on broker config dirs and on docker-compose / `.env` bundles:

```sh
python3 detector.py path/to/configs/
```

Exit code = number of files with at least one finding (capped at
255). Stdout: `<file>:<line>:<reason>`.

## Safe pattern

```conf
listener 1883 0.0.0.0
allow_anonymous false
password_file /mosquitto/config/passwd
```

with `mosquitto_passwd` provisioning real users. For machine-to-
machine, prefer `listener 8883`, `require_certificate true`, and
mTLS via `cafile` / `certfile` / `keyfile`.

## Refs

- CWE-306: Missing Authentication for Critical Function
- CWE-1188: Insecure Default Initialization of Resource
- OWASP IoT Top 10 (2018) I1
- Eclipse Mosquitto 2.0 release notes — "anonymous connections are
  no longer allowed by default"

## Verify

```sh
bash verify.sh
```

Should print `bad=5/5 good=0/3 PASS`.

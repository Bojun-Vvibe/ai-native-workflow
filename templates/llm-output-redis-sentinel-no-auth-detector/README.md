# llm-output-redis-sentinel-no-auth-detector

Detect Redis **Sentinel** configurations that LLMs commonly emit with no
authentication on the control plane. Sentinel is a separate daemon (default
port `26379`) that controls master election and failover. If it is reachable
without a password, an attacker can call `SENTINEL FAILOVER` to demote the
real master, call `SENTINEL SET` to mutate per-monitor configuration, or
read full topology with `SENTINEL MASTERS` / `SLAVES`. It also needs to know
the **data-plane** password to reach a protected master, via
`sentinel auth-pass <name> <password>`. LLMs that "just get it working"
routinely emit configs missing every one of these.

This detector is orthogonal to `llm-output-redis-no-requirepass-detector`
and `llm-output-redis-bind-0000-detector` (which target the data-plane
`redis-server`). This one only fires for **Sentinel** files / invocations.

Related weaknesses: CWE-306 (Missing Authentication for Critical Function),
CWE-1188 (Insecure Default Initialization of Resource).

## What bad LLM output looks like

A `sentinel.conf` listening on every interface with no password:

```
port 26379
bind 0.0.0.0
sentinel monitor mymaster 10.0.5.1 6379 2
```

A `sentinel.conf` that monitors a master but never declares
`sentinel auth-pass` for it (Sentinel cannot authenticate to the data
plane and will mis-report the master as down):

```
sentinel monitor cache-prod 10.20.30.40 6379 2
requirepass s3cretSentinelPassw0rd
```

`protected-mode no` on a Sentinel with no `requirepass`:

```
protected-mode no
sentinel monitor mymaster 192.168.1.10 6379 2
sentinel auth-pass mymaster redisDataPass
```

A Dockerfile baking the open-mode invocation into `CMD`:

```dockerfile
CMD ["redis-sentinel", "/etc/redis/sentinel.conf", "--bind", "0.0.0.0", "--protected-mode", "no"]
```

## What good LLM output looks like

- Sentinel binds to a loopback or private-subnet address, sets
  `requirepass`, and declares `sentinel auth-pass <name> <secret>` for
  every `sentinel monitor` line.
- `sentinel auth-user` + `sentinel auth-pass` is used when the data
  plane has Redis ACLs enabled.
- `sentinel sentinel-pass` is set so peer Sentinels also authenticate.
- Plain (non-Sentinel) `redis.conf` files are out of scope and never
  flagged here — see the `redis-no-requirepass` detector for those.

## Run the smoke test

```sh
bash detect.sh samples/bad/* samples/good/*
```

Expected output:

```
BAD  samples/bad/dockerfile_sentinel_open.Dockerfile
BAD  samples/bad/sentinel_bind_all_no_pass.conf
BAD  samples/bad/sentinel_monitor_without_auth_pass.conf
BAD  samples/bad/sentinel_protected_mode_no.conf
GOOD samples/good/dockerfile_sentinel_with_pass.Dockerfile
GOOD samples/good/plain_redis_not_sentinel.conf
GOOD samples/good/sentinel_loopback_full_auth.conf
GOOD samples/good/sentinel_private_iface_with_auth.conf
bad=4/4 good=0/4 PASS
```

Exit status is `0` only when every bad sample is flagged and zero good
samples are flagged.

## Detector rules

A file is in scope only if it contains one of `sentinel monitor`,
`redis-sentinel`, `--sentinel`, or `port 26379`. Plain `redis.conf` data-
plane files are intentionally ignored.

For **config-style** files (those with a `sentinel monitor` directive):

1. Bound to a non-loopback address (or no `bind` line at all) AND no
   `requirepass` AND no `sentinel sentinel-pass`.
2. A `sentinel monitor <name> <host> <port> <quorum>` line with no
   matching `sentinel auth-pass` anywhere in the file.
3. `protected-mode no` with no `requirepass`.

For **invocation-style** snippets (Dockerfile `CMD`, compose `command:`,
entrypoint scripts running `redis-sentinel` or `--sentinel`):

4. Explicit `--bind 0.0.0.0` or `--protected-mode no` on the same line
   AND no `--requirepass <secret>` argument. JSON-array `CMD ["...","..."]`
   form is normalized so flags split across array elements still match.

Shell `#` comments are stripped before matching.

## Known false-positive notes

- A Sentinel running inside a private network namespace where every peer
  is mTLS-authenticated at L4 may legitimately omit `requirepass`; this
  detector cannot see the network policy and will still flag it. Treat
  as a documentation prompt rather than a hard block.
- `auth-user` without `auth-pass` is rare but valid when Redis ACLs use
  certificate-based auth. The detector requires `auth-pass`; suppress
  per-file via your repo's existing detector-suppression mechanism.

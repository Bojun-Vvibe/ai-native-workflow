# llm-output-adguardhome-no-auth-public-detector

Detects AdGuard Home (`AdGuardHome.yaml`) configurations that expose
the admin web UI / DNS API without authentication — or with default
/ placeholder credentials — while binding to a non-loopback address.

## Why this matters

AdGuard Home is a self-hosted DNS resolver + filter. Admin UI access
gives an attacker the ability to:

* Add malicious upstreams (silently MITM every DNS lookup).
* Add DNS rewrites pointing real domains at attacker IPs.
* Reconfigure DHCP options on any LAN where it serves DHCP.
* Read the full DNS query log of every client.

The shipped post-install `AdGuardHome.yaml` literally contains an
empty `users: []` block until the first-run setup wizard is
completed. LLMs that emit AdGuardHome compose / Helm snippets
frequently skip the wizard step and ship that empty block straight
through.

## What it flags

1. `users:` missing or empty AND `bind_host` / `http.address`
   resolves to a non-loopback host.
2. `users[]` entries whose `password` is empty, a placeholder
   (`<bcrypt-hash>`, `changeme`, …), or not a bcrypt hash at all
   (bcrypt hashes must start with `$2a$`, `$2b$`, or `$2y$`).
3. Weak username (`admin`, `root`, `test`, `user`, `adguard`) paired
   with a bcrypt cost below 10.
4. `auth_attempts: 0` or `block_auth_min: 0` — disables the
   brute-force lock-out.

## Suppression

```
# adguardhome-no-auth-public-allowed
```

## CWE refs

* CWE-306: Missing Authentication for Critical Function
* CWE-521: Weak Password Requirements
* CWE-1188: Insecure Default Initialization of Resource

## Usage

```
python3 detector.py <path> [<path> ...]
```

Exit code = number of files with findings (capped 255).
Stdout: `<file>:<line>:<reason>`.

## Verify

```
./verify.sh
```

Expected: `bad=4/4 good=0/4 PASS`.

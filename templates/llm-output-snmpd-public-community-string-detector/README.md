# llm-output-snmpd-public-community-string-detector

Static lint that flags Net-SNMP / `snmpd.conf` (and docker-compose
env / .env style) configurations that expose the well-known
community strings `public` or `private` on a non-loopback listener.

SNMPv1 and SNMPv2c authenticate with a single shared "community
string". The defaults are `public` (read-only) and `private`
(read-write). Anyone who can reach UDP/161 with the right string
can walk the entire MIB — including `hrSWRunName`, ARP tables,
network interface counters, and on routers, full configurations
via `.iso.org.dod.internet.private.enterprises`. With `private`
they can rewrite config. LLMs asked "give me a working snmpd.conf
for monitoring" routinely emit `rocommunity public` because that
makes `snmpwalk -v2c -c public ... .` return data on the first try.

## Why LLMs emit this

* Net-SNMP example configs and most tutorials lead with
  `rocommunity public` — it is the minimum line that makes snmpd
  respond.
* Docker images for monitoring stacks (Telegraf SNMP input, LibreNMS
  test harnesses) ship demo configs with `public`.
* Network-vendor docs frequently demonstrate SNMPv2c with `public`
  for "show me how to enable monitoring" snippets, which the model
  then emits verbatim.

## What it catches

Per file (line-level):

- `rocommunity public` / `rocommunity6 public`
- `rwcommunity private` / `rwcommunity6 private`
- `rocommunity public <source>` where `<source>` is `default` /
  `0.0.0.0/0` / `::/0` / a public CIDR
- `com2sec <name> default public` (older Net-SNMP form)
- `community public` (Cisco-style snippet)
- env-vars `SNMP_COMMUNITY=public` /
  `SNMPD_COMMUNITY=public` / `SNMP_RO_COMMUNITY=public` /
  `SNMP_RW_COMMUNITY=private` (compose / .env)

Per file (whole-file):

- A non-loopback `agentaddress` directive AND no `createUser` /
  `usmUser` / `rouser` / `rwuser` (i.e., no SNMPv3 user defined).

## What it does NOT flag

- `rocommunity public 127.0.0.1` / loopback / `localhost`.
- `rouser monitor authPriv` (SNMPv3 with auth+priv).
- Lines with a trailing `# snmp-pub-ok` comment.
- Files containing `# snmp-pub-ok-file` anywhere.
- Blocks bracketed by `# snmp-pub-ok-begin` / `# snmp-pub-ok-end`.

## How to detect (the pattern)

```sh
python3 detector.py path/to/configs/
```

Exit code = number of files with at least one finding (capped at
255). Stdout: `<file>:<line>:<reason>`.

## Safe pattern

```conf
# snmpd.conf — SNMPv3 only, USM user with authPriv
agentaddress udp:0.0.0.0:161
createUser monitor SHA "longRandomAuthPass" AES "longRandomPrivPass"
rouser monitor authPriv
```

For SNMPv2c that you genuinely cannot retire, restrict by source
and use a long random community string:

```conf
rocommunity 9bfA3xR7tK2qV-readonly 10.0.5.0/24
```

## Refs

- CWE-521: Weak Password Requirements
- CWE-798: Use of Hard-coded Credentials
- CWE-1188: Insecure Default Initialization of Resource
- US-CERT TA17-156A — SNMP default community strings
- RFC 3414 §1.2 — USM (SNMPv3) was introduced specifically because
  v1/v2c community strings are sent in clear text

## Verify

```sh
bash verify.sh
```

Should print `bad=5/5 good=0/3 PASS`.

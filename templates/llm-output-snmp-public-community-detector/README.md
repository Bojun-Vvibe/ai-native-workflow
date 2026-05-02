# llm-output-snmp-public-community-detector

Detects LLM-generated SNMP daemon configuration (`snmpd.conf`,
`snmptrapd.conf`, NET-SNMP fragments) that exposes the device with the
default `public` (read) or `private` (write) v1/v2c community strings.

## Why this matters

SNMP v1/v2c communities are bearer tokens transmitted in cleartext. The
defaults `public` (RO) and `private` (RW) are universally known and
scanned for by every internet-facing botnet. Combined with a non-local
`agentAddress` they grant unauthenticated read of system inventory and,
with `private`, remote write of arbitrary OIDs (interface state, route
tables, etc).

LLM output frequently produces snippets like:

```
rocommunity public  default
rwcommunity private 10.0.0.0/8
agentAddress udp:161
```

…which is exactly the legacy default and should never reach production.

## What this checks

For each input file the detector flags:

1. `rocommunity` / `rocommunity6` lines whose community token equals
   `public` (case-insensitive).
2. `rwcommunity` / `rwcommunity6` lines whose community token equals
   `private` (case-insensitive).
3. Legacy `com2sec` entries that map a name to community `public` or
   `private`.
4. Pre-NET-SNMP-style `community public` / `community private` one-liners
   used by some embedded daemons (Cisco IOS-style fragments, snmpwalk
   examples shipped as configuration).

A file with **any** match is reported. Per-line output:
`<file>:<line>:<reason>`. Exit code = number of files with at least one
finding (capped at 255 so shells can use it as a count).

## False-positive surface

* Pure documentation that mentions `public` only inside a Markdown
  fenced block tagged `text` is **not** a config file; users should run
  the detector against extracted config artefacts, not prose.
* Files containing the suppression marker `# snmp-public-allowed` on
  any line are skipped (e.g. lab fixtures).
* `rocommunity public 127.0.0.1` is **still** flagged: the convention
  `127.0.0.1` does not protect against local privilege escalation and
  the token itself is the published default.

## CWE refs

* CWE-798: Use of Hard-coded Credentials
* CWE-521: Weak Password Requirements
* CWE-319: Cleartext Transmission of Sensitive Information

## Usage

```sh
python3 detector.py path/to/snmpd.conf [more.conf ...]
./verify.sh   # runs against bundled fixtures, prints PASS/FAIL
```

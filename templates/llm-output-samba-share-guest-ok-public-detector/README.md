# llm-output-samba-share-guest-ok-public-detector

Detects Samba (`smb.conf`) share definitions that combine
`guest ok = yes` (or `public = yes`) with `read only = no` /
`writable = yes` and **no** restriction on `valid users`,
`hosts allow`, or `force user` to a non-`nobody` account — i.e. a
world-writable, unauthenticated SMB share.

Also flags a global `[global]` section that sets
`map to guest = bad user` together with any writable, guest-ok share,
because that combination silently maps every failed login to the
guest account.

## Why this matters

A writable guest-ok Samba share on a network-reachable interface is a
ransomware drop point and a classic data-exfil staging path. The
combination

    [shared]
        path = /srv/shared
        guest ok = yes
        writable = yes

at file-server defaults makes the share accessible to every host on
the LAN with no credential challenge, including any compromised
laptop. LLM-generated quickstart configs frequently emit exactly this
shape because it is the shortest path to a "working" share.

## What it detects

For every share section in an `smb.conf`-style file, the detector
flags it when **all** of:

1. The section is **not** `[global]`, `[printers]`, or `[homes]`.
2. The share is guest-accessible: `guest ok = yes` (or `yes`,
   `true`, `1`) — or `public = yes` (the legacy alias).
3. The share is writable: `writable = yes`, `writeable = yes`,
   `read only = no`, or `read only = false`.
4. None of the following access restrictions are present in the
   section:
   - `valid users = ...`
   - `hosts allow = ...` (or the alias `allow hosts = ...`)
   - `force user = <user>` where `<user>` is **not** `nobody` /
     `guest`.

It also reports a finding when `[global]` contains
`map to guest = bad user` **and** the file has at least one
writable guest-ok share — that combination converts every failed
auth to a guest write.

## CWE references

- CWE-276: Incorrect Default Permissions
- CWE-284: Improper Access Control
- CWE-306: Missing Authentication for Critical Function

## False-positive surface

- A share intentionally exposed to anonymous read/write on an
  air-gapped lab host. Suppress per file with a top comment
  `; smb-public-write-allowed` (Samba uses `;` and `#` for
  comments).
- The `[printers]` and `[homes]` sections are skipped because they
  have their own semantics.

## Usage

    python3 detector.py path/to/smb.conf

Exit code: number of files with at least one finding (capped at
255). Stdout format: `<file>:<line>:<reason>`.

Run `bash verify.sh` to execute the bundled good/bad fixtures.

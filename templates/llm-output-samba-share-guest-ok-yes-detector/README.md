# llm-output-samba-share-guest-ok-yes-detector

Detects Samba (`smb.conf`) share definitions that ship with
`guest ok = yes` (or its alias `public = yes`) on a share that is
reachable from the network and where the global `[global]` section
has `map to guest` configured to actually translate unauthenticated
sessions to the guest account.

## Why this matters

`guest ok = yes` on an SMB share, combined with
`map to guest = bad user` (a very common shape in tutorials), turns
that share into an **anonymous, no-password file service** for any
client that can reach TCP 445. Read-only exposure leaks file contents;
`writable = yes` on top means an unauthenticated client can drop or
overwrite files — and SMB shares are a classic ransomware staging
ground.

LLM-generated `smb.conf` snippets routinely emit shapes like:

```ini
[global]
   map to guest = bad user

[public]
   path = /srv/samba/public
   guest ok = yes
   writable = yes
```

because that's the minimum config to make `smbclient //host/public`
"just work" with no credentials. The detector flags that shape so the
LLM caller can intercept it before the share lands in a real
deployment.

## What it detects

For each scanned file, the detector parses the `[global]` defaults
and every share section, and reports a finding when **all** of:

1. The share is not `[global]`, `[printers]`, or `[print$]`.
2. The share has `guest ok = yes` (or alias `public = yes`).
3. `[global]` has `map to guest` set to `bad user`, `bad password`, or
   `bad uid` — meaning unauthenticated clients are actually routed to
   the guest account. If `map to guest` is unset or `never`, the
   guest grant is inert and not flagged.
4. The server is **not** loopback-only — both
   `interfaces = 127.0.0.1` (or `lo`) and `bind interfaces only = yes`
   would have to be set to suppress the finding.
5. The file does not contain a top-level
   `# smb-guest-allowed` suppression marker.

`writable = yes` / `read only = no` is recorded so the finding text
labels the share as "anonymous **write** access" (vs read-only), but
read-only anonymous shares are still flagged.

## CWE references

- CWE-284: Improper Access Control
- CWE-306: Missing Authentication for Critical Function
- CWE-538: Insertion of Sensitive Information into Externally-Accessible File or Directory
- CWE-732: Incorrect Permission Assignment for Critical Resource

## False-positive surface

- Genuinely intentional kiosk / public-info shares. Suppress per file
  with a top comment `# smb-guest-allowed`.
- A share with `guest ok = yes` but global `map to guest = never`
  cannot actually be entered without credentials and is NOT flagged.
- The detector does not parse `include = …` directives; defaults
  defined in a separate file are not seen.

## Usage

    python3 detector.py path/to/smb.conf

Exit code: number of files with at least one finding (capped at 255).
Stdout format: `<file>:<line>:<reason>`.

Run `bash verify.sh` to execute the bundled good/bad fixtures.

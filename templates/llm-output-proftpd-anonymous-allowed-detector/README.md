# llm-output-proftpd-anonymous-allowed-detector

Stdlib-Python detector for `proftpd.conf` snippets that leave an
`<Anonymous>` block enabled without locking down login.

## What it spots

For each active (uncommented) `<Anonymous ...> ... </Anonymous>`
block, the detector reports a finding when the block does **not**
contain any of:

- `<Limit LOGIN> ... DenyAll | DenyUser <…> | DenyGroup <…> ... </Limit>`
- `AnonRequirePassword on`

Multiple `<Anonymous>` blocks are evaluated independently — any
unhardened block produces a finding.

## Why it matters

A bare `<Anonymous>` block in ProFTPD accepts logins as
`anonymous` / `ftp` (or whatever `User` directive aliases) with
the email-as-password convention only — there is no real
authentication. Combined with a `<Limit STOR>AllowAll</Limit>`
or a missing write limit, it turns the host into open file
storage; even read-only it leaks whatever the anon directory
maps to.

This is the canonical CWE-284 / CWE-287 finding for FTP and is
what NVD scanners flag as "Anonymous FTP allowed". LLM-generated
ProFTPD configs frequently emit the upstream example block
verbatim — the example was never meant to be a production
default — so this detector targets exactly that shape.

## Usage

```
python3 detector.py path/to/proftpd.conf
python3 detector.py examples/bad
```

Exit code is the number of files with at least one finding (capped
at 255). Each finding line is `<file>:<line>:<reason>`, where
`<line>` points at the `<Anonymous ...>` opener.

## Smoke test

```
$ ./smoke.sh
bad=4/4 good=0/4
PASS
```

Bad fixtures cover: classic Linux-distro example block, world-
writable drop-box, multiple anon blocks in one file, and a
`<Limit>` that targets the wrong scope (READ/WRITE instead of
LOGIN). Good fixtures cover: explicit `<Limit LOGIN>DenyAll`,
`AnonRequirePassword on`, fully-commented anon block, and the
`# proftpd-anonymous-allowed` lab marker (intentional read-only
public mirror).

## How to extend

- Track `<Limit STOR>` / `<Limit WRITE>` inside the anon block
  and raise severity when uploads are also allowed.
- Cross-reference `MaxClients` and `MaxClientsPerHost` — an
  anon-open server with no client cap is a trivial DoS surface.
- Add a sibling check for `mod_anonymous` being explicitly
  loaded (`LoadModule mod_anonymous.c`) while the same file
  defines no `<Anonymous>` block — usually a misconfig that
  enables a default surface.
- Walk into ProFTPD's `Include` files (`proftpd.conf.d/*.conf`)
  using the same path-globbing strategy as the other config
  detectors in this directory.

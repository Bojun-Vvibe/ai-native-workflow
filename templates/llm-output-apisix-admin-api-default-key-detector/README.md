# llm-output-apisix-admin-api-default-key-detector

Detects Apache APISIX `config.yaml` files that ship the upstream
default Admin API key (`edd1c9f034335f136f87ad84b625c8f1` for `admin`,
`4054f7cf07e344346cd3f287985e76a2` for `viewer`) while the Admin API
is reachable from a non-loopback interface.

## Why this matters

APISIX's `conf/config-default.yaml` ships with two well-known
`admin_key` values that have remained byte-for-byte unchanged across
many releases. Every quickstart, every Docker-compose tutorial, and
nearly every LLM-generated APISIX scaffold pastes the same key:

    admin_key:
      - name: admin
        key: edd1c9f034335f136f87ad84b625c8f1
        role: admin

Anyone who can reach `:9180` (the default Admin API port) with that
key can register routes, swap upstreams, and load Lua plugins —
which is full data-plane RCE. The default `allow_admin` is
`0.0.0.0/0`, so a freshly deployed APISIX with the default key is
remotely controllable by anyone who can reach it.

## What it detects

For each scanned `config.yaml`/`config.yml`, the detector reports a
finding when:

1. The file contains an `admin_key` list whose `key:` value is one of
   the two upstream defaults.
2. AND the Admin API is exposed beyond loopback. This is true when:
   - `admin_listen.ip` is not `127.0.0.1` / `localhost` / `::1`, OR
   - `allow_admin:` lists any non-loopback CIDR, OR
   - `allow_admin:` is omitted entirely (APISIX defaults to
     `0.0.0.0/0`).

## CWE references

- CWE-798: Use of Hard-coded Credentials
- CWE-1188: Insecure Default Initialization of Resource
- CWE-306: Missing Authentication for Critical Function

## False-positive surface

- `admin_listen.ip = 127.0.0.1` (or `::1` / `localhost`) is treated as
  a dev sandbox and ignored.
- An `allow_admin:` block whose every entry is loopback (`127.0.0.0/24`,
  `127.0.0.1`, `::1`) is also ignored.
- A file that intentionally documents the default key (e.g. a
  hardening tutorial showing the BAD example) can be suppressed with
  a top-of-file comment `# apisix-default-key-allowed`.

## Usage

    python3 detector.py path/to/config.yaml

Exit code: number of files with at least one finding (capped at 255).
Stdout format: `<file>:<line>:<reason>`.

Run `bash verify.sh` to execute the bundled good/bad fixtures.

## Worked example

Real, captured output from `bash verify.sh` against the bundled
fixtures:

    bad=4/4 good=0/4
    PASS

Per-fixture detector output (`python3 detector.py examples/bad/*`):

    examples/bad/01_default_admin_key_all_ifaces.yaml:5:deployment.admin.admin_key uses upstream default admin key edd1c9f034335f136f87ad84b625c8f1 on Admin API bind=0.0.0.0
    examples/bad/02_allow_admin_world.yaml:4:deployment.admin.admin_key uses upstream default admin key edd1c9f034335f136f87ad84b625c8f1 on Admin API bind=allow_admin=['0.0.0.0/0']
    examples/bad/02_allow_admin_world.yaml:7:deployment.admin.admin_key uses upstream default viewer key 4054f7cf07e344346cd3f287985e76a2 on Admin API bind=allow_admin=['0.0.0.0/0']
    examples/bad/03_default_key_internal_subnet.yaml:5:deployment.admin.admin_key uses upstream default admin key edd1c9f034335f136f87ad84b625c8f1 on Admin API bind=allow_admin=['10.0.0.0/8', '192.168.1.0/24']
    examples/bad/04_quickstart_paste.yaml:9:deployment.admin.admin_key uses upstream default admin key edd1c9f034335f136f87ad84b625c8f1 on Admin API bind=192.0.2.10

The good fixtures all return exit 0 with no output: rotated key,
loopback bind, loopback-only allow_admin, and the suppressed
hardening tutorial.

## LLM-output detection prompt

When reviewing LLM-generated APISIX configuration, flag any output
that contains `edd1c9f034335f136f87ad84b625c8f1` or
`4054f7cf07e344346cd3f287985e76a2` as a literal `key:` value unless
the surrounding context constrains the Admin API to loopback. The
default keys are public and indexed by every internet scanner — they
must be rotated before the gateway accepts traffic from anything
beyond `lo`.

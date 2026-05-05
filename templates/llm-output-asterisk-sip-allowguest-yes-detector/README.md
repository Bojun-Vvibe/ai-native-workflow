# llm-output-asterisk-sip-allowguest-yes-detector

Static lint that flags Asterisk SIP / `chan_sip` / `pjsip`
configurations that leave `allowguest = yes` (or its `pjsip`
equivalent — an endpoint with no `auth` and an `identify` block
whose `match` is `0.0.0.0/0`) on a publicly reachable PBX.

When `allowguest = yes` is set in `sip.conf [general]`, Asterisk
accepts INVITEs from peers it has no credentials for and routes
them through the dialplan. Combined with a permissive dialplan
this is the canonical "phone bill in the morning" misconfiguration:
attackers place toll-fraud calls to premium-rate numbers via PSTN
trunks, with no authentication.

For pjsip the equivalent shape is an endpoint named `anonymous`
(or with empty `auth`) used by an `identify` section that does not
restrict `match` to a known peer subnet.

## Why LLMs emit this

* The historic `chan_sip` default for `allowguest` was `yes`,
  and most pre-Asterisk-13 sample configs and tutorials never
  flip it.
* "Quick start" SIP guides leave `[general]` minimal and only
  define one peer, leaving guests on by default.
* Compose stacks for softphone demos hard-code `allowguest=yes`
  so a freshly-pulled image lets the test client connect with
  no extension provisioning.

## What it catches

Per file (line-level):

- `allowguest = yes|true|1|on` in any section (chan_sip).
- `alwaysauthreject = no` (extension enumeration via auth-failure
  oracle).
- `autocreatepeer = yes` (chan_sip auto-trusts arbitrary peers).
- `insecure = invite,...` on a `type=peer`/`type=friend` whose
  ACL does not deny `0.0.0.0/0` and permit a specific subnet.
- pjsip endpoint with empty/omitted `auth` paired with an
  `identify` section whose `match` is `0.0.0.0/0`, `::/0`, or
  `any` (or any pjsip endpoint named `anonymous` with no auth).

Per file (whole-file):

- `sip.conf`-shape file (has `[general]` and references SIP
  knobs) where `allowguest` is unset — chan_sip's historic
  default is `yes`.

## What it does NOT catch

- `allowguest = no`.
- `insecure = invite` on a peer that also has `deny = 0.0.0.0/0`
  and `permit = <specific subnet>`.
- Lines marked with trailing `; sip-guest-ok` / `# sip-guest-ok`.
- Files containing `# sip-guest-ok-file` anywhere.
- Blocks bracketed by `# sip-guest-ok-begin` /
  `# sip-guest-ok-end`.

## Usage

```
python3 detector.py <file_or_dir> [...]
```

Exit code = number of files with at least one finding (capped at 255).
Stdout lines = `<file>:<line>:<reason>`.

## Verify

```
bash verify.sh
```

Expected: `bad=N/N good=0/M PASS`.

## Refs

- CWE-284 Improper Access Control
- CWE-306 Missing Authentication for Critical Function
- CWE-1188 Insecure Default Initialization of Resource
- AST-2009-003 — `allowguest` and SIP toll fraud

# llm-output-vsftpd-anonymous-enable-yes-detector

Detects LLM-emitted `vsftpd.conf` snippets and Dockerfiles that enable
anonymous FTP access — and especially the much worse case where the
anonymous user is also given write / upload / mkdir permissions, turning
the server into an open relay for arbitrary file drops.

This is distinct from the generic `llm-output-ftp-anonymous-login-detector`
template: this one is tightly scoped to vsftpd's actual directive syntax
(`anonymous_enable=YES`, `anon_upload_enable=YES`, `anon_mkdir_write_enable=YES`,
`write_enable=YES`, `no_anon_password=YES`) so it works on real config files
that wouldn't trip a string match for "anonymous login".

CWE-285 (Improper Authorization) and CWE-269 (Improper Privilege Management)
when anonymous write is enabled; CWE-287 (Improper Authentication) for the
read-only anonymous case.

## What this catches

| # | Pattern                                                                                       |
|---|-----------------------------------------------------------------------------------------------|
| 1 | `anonymous_enable=YES` combined with any of the anon write directives set to `YES`            |
| 2 | `anonymous_enable=YES` combined with `write_enable=YES` (anon inherits write)                 |
| 3 | `no_anon_password=YES` (skip even the placeholder email prompt) with `anonymous_enable=YES`   |
| 4 | Dockerfile that bakes `anonymous_enable=YES` into a vsftpd image without a downstream override |

## Usage

```bash
python3 detector.py examples/bad/* examples/good/*
```

Exit 0 iff every bad sample fires and zero good samples fire. Final stdout
line: `bad=N/N good=0/M PASS|FAIL`.

## Worked example

Run `./run-test.sh` from this directory. It executes the detector against
the bundled samples and asserts `bad=4/4 good=0/3 PASS`.

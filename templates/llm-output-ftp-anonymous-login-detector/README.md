# llm-output-ftp-anonymous-login-detector

Static lint that flags FTP server configurations that allow anonymous
login.

Anonymous FTP exposes files without authentication. While that was a
deliberate "public file drop" pattern in the 1990s, modern LLM output
frequently emits anonymous-FTP shapes inside production
`vsftpd.conf` / `proftpd.conf` / `pure-ftpd` flag sets and Dockerfile
`RUN` lines, often combined with a writable upload directory. That
combination becomes a malware drop / pivot box: the anonymous user
can upload arbitrary content, which downstream HTTP servers may then
serve or execute.

LLM-generated FTP configs routinely paste in:

```conf
# vsftpd.conf
anonymous_enable=YES
anon_upload_enable=YES
anon_mkdir_write_enable=YES
no_anon_password=YES
```

```conf
# proftpd.conf
<Anonymous /srv/ftp>
    User ftp
    AnonRequirePassword off
    <Limit WRITE>
        AllowAll
    </Limit>
</Anonymous>
```

This detector flags those shapes.

## What it catches

- **vsftpd**: `anonymous_enable=YES`. Stronger finding when paired
  with `anon_upload_enable=YES`, `anon_mkdir_write_enable=YES`, or
  `no_anon_password=YES`. Trifecta finding emitted when anonymous
  login + anon write are both on.
- **proftpd**: `<Anonymous>` block with no `AnonRequirePassword on`,
  or with explicit `AnonRequirePassword off`.
- **pure-ftpd**: flag file `NoAnonymous=no`, or Dockerfile-style
  invocation that doesn't pass `-E` / `--noanonymous`.
- Same shapes inside Dockerfile `RUN`/`CMD` lines.

## CWE references

- [CWE-287](https://cwe.mitre.org/data/definitions/287.html):
  Improper Authentication
- [CWE-732](https://cwe.mitre.org/data/definitions/732.html):
  Incorrect Permission Assignment for Critical Resource
- [CWE-276](https://cwe.mitre.org/data/definitions/276.html):
  Incorrect Default Permissions

## False-positive surface

- A file containing the comment `# ftp-anonymous-allowed` is treated
  as an explicit public-drop config and skipped wholesale.
- `anonymous_enable=NO` is safe.
- proftpd `<Anonymous>` blocks with explicit `AnonRequirePassword on`
  are safe.
- `anon_root=/var/empty` (chrooted to an empty dir) suppresses the
  trifecta upgrade.

## Worked example

```sh
$ ./verify.sh
bad=4/4 good=0/3
PASS
```

## Files

- `detector.py` — scanner. Exit code = number of files with at least
  one finding.
- `verify.sh` — runs all `examples/bad/` and `examples/good/` and
  reports `bad=X/X good=0/Y` plus `PASS` / `FAIL`.
- `examples/bad/` — expected to flag.
- `examples/good/` — expected to pass clean.

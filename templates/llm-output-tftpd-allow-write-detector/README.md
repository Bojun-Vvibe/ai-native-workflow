# llm-output-tftpd-allow-write-detector

Detect `tftpd-hpa` / `in.tftpd` configuration that puts the daemon into
write-enabled mode, i.e. allows anonymous file uploads/overwrites over
UDP/69. TFTP has **no authentication, no integrity, no transport
encryption** — anyone who can reach the port can drop arbitrary content
into the TFTP root, which on a typical PXE / network-boot deployment
means overwriting bootloaders, kernel images, or switch firmware.

This detector is intentionally distinct from the various
`*-no-auth-detector` templates in this repo: TFTP never had auth in the
first place, so there is no "auth toggle" to flip. The only real switch
is **whether writes are accepted at all**, controlled by the
`-c` / `--create` flag passed to `in.tftpd`. We flag exactly that flag,
scoped to the lines where it matters (the `OPTIONS=` / `TFTP_OPTIONS=`
assignment in `/etc/default/tftpd-hpa`, the `ExecStart=` line of the
systemd unit, or a bare `/usr/sbin/in.tftpd …` invocation in a script).

LLMs commonly emit `--create` or `-c` when asked to "set up tftpd so
PXE clients can upload their config back" — the official man page
mentions it as an option, and the model picks the path of least
resistance.

## What bad LLM output looks like

Debian default file with `--create`:

```sh
# /etc/default/tftpd-hpa
TFTP_OPTIONS="--secure --create"
```

Short-flag form:

```sh
TFTP_OPTIONS="--secure -c"
```

systemd unit override:

```ini
[Service]
ExecStart=
ExecStart=/usr/sbin/in.tftpd --listen --user tftp --address :69 --secure --create /srv/tftp
```

Bare invocation in a provisioning script with grouped short flags:

```sh
exec /usr/sbin/in.tftpd -L --secure -cv --user tftp /srv/tftp
```

## What good LLM output looks like

Same daemon, no write enablement:

```sh
TFTP_OPTIONS="--secure"
```

Or:

```ini
ExecStart=/usr/sbin/in.tftpd --listen --user tftp --address :69 --secure -v /srv/tftp
```

A file that is unrelated to `tftpd` — e.g. an SSH config that uses `-c`
for cipher selection — is **not** flagged, because the file does not
match the `in.tftpd` / `tftpd-hpa` heuristic. See `samples/good-3.txt`.
A documentation file that *mentions* `--create` only inside a comment
is also not flagged, because comment-only lines are skipped before the
options scan. See `samples/good-4.txt`.

## How the detector decides

1. Decide that the file is tftpd-related: it must mention `tftpd-hpa`,
   `in.tftpd`, `/usr/sbin/in.tftpd`, one of `TFTP_OPTIONS` /
   `TFTP_DIRECTORY` / `TFTP_USERNAME`, or a systemd `Description=`
   value containing `tftp`. If none of those appear, do not flag.
2. Skip lines that are pure `#` or `;` comments. Strip trailing `#`
   comments before scanning.
3. Identify a "payload" string per line — only one of:
   - an `OPTIONS=` / `TFTP_OPTIONS=` / `ARGS=` / `DAEMON_OPTS=` shell
     assignment,
   - an `ExecStart=` line whose value contains `in.tftpd` or
     `tftpd-hpa`,
   - a line containing `in.tftpd` followed by whitespace (a bare
     invocation in a shell script).
4. Inside that payload, normalize quotes to whitespace, then flag if
   any token equals `--create` or any single-dash short-flag group
   (e.g. `-c`, `-cv`, `-vc`, `-vcs`) contains a literal `c`. This
   correctly handles both the long form and grouped short-flag form
   without matching `--create-foo` or unrelated long options.

## Running

```sh
./run-tests.sh
```

Expected output ends with:

```
bad=4/4 good=0/4 PASS
```

`detect.sh` exits non-zero on any FAIL, so the script is safe to drop
into a pre-commit / CI hook over a directory of LLM-emitted snippets.

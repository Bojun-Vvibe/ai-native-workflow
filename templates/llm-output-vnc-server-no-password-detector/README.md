# llm-output-vnc-server-no-password-detector

Detects VNC server launch commands and config files that expose a
graphical desktop with **no authentication** — typically `x11vnc`,
`tigervnc`, `tightvnc`, `vncserver`, or container images run with
`-nopw`, `-SecurityTypes None`, or an empty `passwd` file.

## Why this matters

A VNC server with no password is equivalent to publishing the user's
entire desktop session to anyone who can reach the TCP port (default
`5900` + display). Attackers routinely sweep `5900-5910` for these
and join silently. Even when the server is bound to localhost,
operators frequently expose it through a reverse SSH tunnel or a
docker `-p 5900:5900` and forget the auth was never set.

LLM-generated tutorials commonly recommend the convenient one-liner

    x11vnc -display :0 -forever -nopw

or container `CMD`s like

    CMD ["vncserver", ":1", "-SecurityTypes", "None"]

because adding a password breaks copy-paste demos. The detector flags
that shape so it can be intercepted before the config lands in a real
deployment.

## What it detects

For each scanned file the detector reports a finding when **any** of:

1. An `x11vnc` invocation contains `-nopw`, `-noauth`, or
   `-passwdfile /dev/null`, **and** does not also bind via
   `-localhost` only.
2. A `tigervnc` / `tightvnc` / `Xvnc` / `vncserver` invocation
   contains `-SecurityTypes None`, `-SecurityTypes none`, or
   `SecurityTypes=None` (case-insensitive) and is not gated by
   `-localhost`.
3. A TigerVNC config file (`config`, `tigervnc.conf`, or any file
   with extension `.tigervnc`) contains a top-level
   `SecurityTypes=None` (or `=none`) directive.
4. A unit/CMD/compose definition launches a VNC server image and
   sets `VNC_PW=""` (empty string) or `VNC_NO_PASSWORD=1` /
   `VNC_NO_PASSWORD=true` while exposing the VNC port.

The detector recognises the following invocation tokens as VNC
servers: `x11vnc`, `vncserver`, `Xvnc`, `tigervnc`, `tightvncserver`,
`tigervncserver`.

## CWE references

- CWE-306: Missing Authentication for Critical Function
- CWE-1188: Insecure Default Initialization of Resource
- CWE-319: Cleartext Transmission of Sensitive Information
  (VNC without TLS / no auth combined)

## False-positive surface

- Strictly local debug sessions where the server is also given
  `-localhost` (or equivalent `-rfbport` bound to `127.0.0.1`) are
  treated as safe.
- Suppress per file with a top-of-file comment containing
  `# vnc-no-auth-allowed`.

## Usage

    python3 detector.py path/to/file_or_dir [more paths ...]

Exit code: number of files with at least one finding (capped at
255). Stdout format: `<file>:<line>:<reason>`.

Run `bash verify.sh` to execute the bundled good/bad fixtures.

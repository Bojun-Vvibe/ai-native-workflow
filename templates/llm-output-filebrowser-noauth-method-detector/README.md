# llm-output-filebrowser-noauth-method-detector

Stdlib-only Python detector that flags **File Browser**
(filebrowser/filebrowser) configurations which disable login by
selecting the `noauth` authentication method or by passing the
`--noauth` CLI flag. Maps to **CWE-306** (missing authentication
for critical function), **CWE-1188** (insecure default initialization
of resource), and **CWE-284** (improper access control).

File Browser is a self-hosted HTTP file manager: browse, upload,
download, rename, share, and (when `commands` is non-empty) execute
configured shell commands from the web UI. With `auth.method =
noauth` every visitor inherits the configured anonymous user. The
quick-start ships that anonymous user with full read/write on the
served root, and the `commands` allowlist is routinely widened to
`["git","sh","bash"]` by users who want "git pull" buttons. Anonymous
access plus a non-empty `commands` list is unauthenticated remote
command execution; even without commands it is unauthenticated read
and write of the served filesystem.

LLMs reach for `noauth` because it is the documented one-line answer
to "I want to share files with my LAN without making accounts" and
to "the login screen breaks my reverse-proxy SSO". The change ships
in a Helm chart or Compose file, the container binds `0.0.0.0:80`,
and the file manager is one port-scan away from anonymous write.

## Heuristic

We flag, outside `#` / `;` / `//` comment lines, any of:

1. JSON directive `"auth.method": "noauth"` (top-level flat form)
   or `"method": "noauth"` (inside an `auth` block).
2. YAML directive `method: noauth` or `auth.method: noauth` in
   filebrowser config / Compose / Helm values.
3. CLI flag `--noauth` to a `filebrowser` invocation (Dockerfile
   CMD/ENTRYPOINT, shell wrapper, systemd `ExecStart`, k8s `args`).
4. `filebrowser config init --auth.method=noauth` or
   `filebrowser config set --auth.method noauth` in setup scripts.
5. Environment-variable override `FB_AUTH_METHOD=noauth` (used by
   the official `filebrowser/filebrowser` image and several
   community Helm charts).

Each occurrence emits one finding line.

## CWE / standards

- **CWE-306**: Missing Authentication for Critical Function.
- **CWE-1188**: Insecure Default Initialization of Resource.
- **CWE-284**: Improper Access Control.
- File Browser docs: `auth.method` defaults to `json` (username +
  password); `noauth` and `proxy` are explicit opt-outs that the
  docs warn must be paired with an upstream auth layer.

## What we accept (no false positive)

- `"auth.method": "json"` (the default), `"proxy"`, or `"hook"`.
- Commented-out lines (`// "auth.method": "noauth"`,
  `# FB_AUTH_METHOD=noauth`).
- Documentation / Markdown mentions (we only scan config-shaped
  files).
- Other keys that happen to share the prefix
  (`auth.method.fallback`, `noauth_redirect_url`).

## Layout

```
detect.py            stdlib-only scanner (regex over text)
smoke.sh             runs detect.py against examples/ and asserts
examples/bad/        4 fixtures that MUST be flagged
examples/good/       4 fixtures that MUST NOT be flagged
```

## Run

```
python3 detect.py path/to/.filebrowser.json
python3 detect.py path/to/repo
bash smoke.sh
```

Exit codes: `0` = clean, `1` = findings, `2` = usage error.

## Why this is a real LLM failure mode

`noauth` is the canonical Stack Overflow / GitHub issue answer to
"how do I disable the filebrowser login screen so my reverse proxy
can SSO me" and to "I just want to share my Downloads folder on the
LAN". An LLM trained on those threads will offer
`"auth.method": "noauth"` or `--noauth` as a one-line fix. The
developer accepts, the Compose file is templated into production,
and the file manager ships open. The detector exists to catch the
paste before it ships.

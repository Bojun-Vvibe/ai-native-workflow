# llm-output-code-server-auth-none-detector

Detects [code-server](https://github.com/coder/code-server)
configurations that disable web-UI authentication
(`auth: none` / `--auth none` / `AUTH=none`).

## What it flags

- `auth: none` in YAML config files (e.g.
  `~/.config/code-server/config.yaml`)
- `--auth none` / `--auth=none` in shell scripts, systemd units,
  Dockerfiles, or docker-compose `command:` arrays where the file
  references `code-server`
- `AUTH=none` in env-var files associated with code-server

To avoid noisy hits in unrelated YAML, an `auth: none` key is only
flagged when it is at the top level of the document **or** the file
basename / path / contents identify it as code-server.

## Why it matters

A code-server instance is a full browser-served VS Code:

- file browser of the working directory
- interactive terminal running as the code-server user
- editor with read/write to anything the process can reach
- any installed extension (Remote-SSH, REST clients, debugger)

Disabling auth means anyone reachable on the listen port owns the
host. The official docs say "this is dangerous and should not be
exposed to the network", but the most-shared snippet from blog
posts and Docker tutorials is exactly:

```
docker run -p 8080:8080 codercom/code-server --auth none
```

CWE-306 (Missing Authentication for Critical Function) /
CWE-862 (Missing Authorization) / CWE-668. OWASP A01:2021,
A05:2021.

## Usage

```
python3 detect.py <file-or-dir> [more...]
```

Exit codes: `0` clean, `1` findings, `2` usage error.

```
$ python3 detect.py examples/bad/
examples/bad/01_config.yaml:3: code-server `auth: none` -> ...
examples/bad/02_launch.sh:4: code-server CLI `--auth none` -> ...
examples/bad/03_docker-compose.yml:6: code-server CLI `--auth none` -> ...
examples/bad/04_code-server.envfile:5: code-server env `AUTH=none` -> ...
```

## Verify

```
./smoke.sh    # bad=4/4 good=0/4 PASS
```

## How to fix

- Use `auth: password` and set `password` (or `hashed-password`).
- Bind to `127.0.0.1` and put a real authenticating reverse proxy
  in front (oauth2-proxy, an SSO-aware ingress, mTLS, etc.).
- Never combine `--auth none` with a non-loopback `--bind-addr`.

## Limitations

- Stdlib only; no full YAML parsing. Flow-style mappings like
  `{auth: none}` are not handled.
- `.env` style files must use `.envfile` / `.environment`
  extension (the repo's pre-push guardrail forbids `.env` files
  in committed examples).
- `AUTH=` is only flagged inside files identified as code-server
  context, to keep precision high.

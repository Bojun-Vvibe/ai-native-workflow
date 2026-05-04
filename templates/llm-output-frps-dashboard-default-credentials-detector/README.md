# llm-output-frps-dashboard-default-credentials-detector

Stdlib-only Python detector that flags **`frps`** (fast reverse
proxy server) configs that expose the admin **dashboard** with the
upstream default credentials (`admin` / `admin`), with another
well-known weak password, or with no credentials at all.

Maps to **CWE-798** (Use of Hard-coded Credentials), **CWE-521**
(Weak Password Requirements), **CWE-1188** (Insecure Default
Initialization), **CWE-306** (Missing Authentication for Critical
Function), OWASP **A07:2021 Identification and Authentication
Failures**.

## What it catches

`frps` ships an HTTP dashboard at `dashboard_addr:dashboard_port`
(default `0.0.0.0:7500`) that lets anyone with network access:

- see every configured proxy and its remote port mapping,
- see every connected client (IP, version, run id),
- close / kick clients,
- reload the server config (frp >= 0.45 with `enable_remote_config`).

The dashboard is gated by HTTP basic-auth, configured via:

- `dashboard_user = "..."` and `dashboard_pwd = "..."` (legacy
  `[common]` INI/TOML form), or
- `[webServer]` table with `user = ...` / `password = ...` (frp
  >= 0.52 TOML), or
- `webServer:` block with `user:` / `password:` (YAML / helm
  values).

The frp README sample shows `dashboard_user = "admin"` and
`dashboard_pwd = "admin"`. LLMs copy that verbatim.

## Heuristic

Flag when the config "looks like" frp (filename contains `frp`, or
file contains `[common]` / `bind_port` / `dashboard_*` / `webServer`)
AND either:

1. `dashboard_pwd` (or `webServer.password`) is one of:
   `admin`, `password`, `admin123`, `frp`, `changeme`, empty string.
2. OR the dashboard is enabled (any `dashboard_addr` /
   `dashboard_port` / `webServer.port` / `webServer.addr` directive)
   AND no password key is set anywhere in the same file.

Do NOT flag:

- frps configs that set `dashboard_pwd` to a non-default value.
- Files without any dashboard / `webServer` directive (dashboard
  off; no exposed surface).
- Lines inside `#`/`;` comments.

## Worked example

```
$ bash smoke.sh
bad=4/4 good=0/4
PASS
```

## Layout

```
examples/bad/
  01_default_admin_admin.ini       # dashboard_pwd = "admin"
  02_no_pwd_set.toml               # dashboard_port set, no dashboard_pwd
  03_webserver_default.toml        # [webServer] password = "admin"
  04_helm_values_no_pwd.yaml       # webServer: { port: 7500 } and no password
examples/good/
  01_strong_pwd.ini                # dashboard_pwd = long random
  02_no_dashboard.toml             # frps without dashboard_*
  03_webserver_strong_pwd.toml     # [webServer] password = randomized
  04_helm_values_strong_pwd.yaml   # webServer: { password: random }
```

## Usage

```bash
python3 detect.py path/to/frps.toml
python3 detect.py path/to/repo/
```

Exit codes: `0` = clean, `1` = findings, `2` = usage error.

## Limits

- We do not parse Helm Sprig templating; values that resolve to a
  default password only after rendering are out of scope.
- We do not chase environment-variable indirection
  (`FRPS_DASHBOARD_PWD=admin`); that form will be added in a
  follow-up if it appears in the wild.
- We accept any non-default password as "safe enough" — no entropy
  analysis. A truly weak custom password (e.g. `"hunter2"`) will
  not be flagged unless it is in the small default-list above.

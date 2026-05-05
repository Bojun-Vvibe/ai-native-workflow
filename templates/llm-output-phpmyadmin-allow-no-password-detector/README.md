# llm-output-phpmyadmin-allow-no-password-detector

Detects LLM-emitted phpMyAdmin configurations that enable
`AllowNoPassword`, letting clients log in to the wrapped
MySQL/MariaDB instance with an empty password. Once a model "fixes" a
login error this way, the resulting config typically ships unchanged
to staging/production and exposes the database to anyone who can
reach the panel.

Maps to CWE-521 (Weak Password Requirements) and CWE-287 (Improper
Authentication).

## What this catches

| # | Pattern                                                                   |
|---|---------------------------------------------------------------------------|
| 1 | PHP: `$cfg['Servers'][$i]['AllowNoPassword'] = true;`                     |
| 2 | PHP: same key set to `1`, `TRUE`, or any non-zero numeric / `"true"`      |
| 3 | Docker env: `PMA_ALLOW_NO_PASSWORD=true` (also `1`, `yes`, `on`)          |
| 4 | Helm/values YAML: `AllowNoPassword: true` under a phpmyadmin block        |

Explicit `false` / `0` and the absence of the key (default `false`)
are treated as good.

## Usage

```bash
python3 detector.py examples/bad/* examples/good/*
```

Exit 0 iff every bad sample fires and zero good samples fire. Final
stdout line: `bad=N/N good=0/M PASS|FAIL`.

## Worked example

Run `./run-test.sh` from this directory. It executes the detector
against the bundled samples and asserts `bad=4/4 good=0/4 PASS`.

# llm-output-gitlab-signup-enabled-true-detector

Static lint that flags self-managed GitLab configurations shipping
with public sign-up enabled.

Public sign-up on a self-hosted GitLab instance lets any
unauthenticated visitor create an account. On a private/internal
instance this is an unauthenticated account-creation primitive that
lets attackers fork internal repos, open issues, abuse CI runners,
and harvest project metadata. The hardened default for an internal
instance is `signup_enabled = false`; LLM-generated `gitlab.rb`
snippets, Helm `values.yaml` files, and bootstrap scripts often paste
in tutorial-style configs that flip it back on:

```ruby
gitlab_rails['signup_enabled'] = true
```

```yaml
appConfig:
  signup_enabled: true
```

This detector flags those shapes while accepting:

- `signup_enabled = false` / `signup_enabled: false`
- files containing `# gitlab-signup-allowed` for instances that
  intentionally allow registration (e.g. a public community server)
- comment lines (`#` prefix)

## What it catches

- Ruby (`gitlab.rb`): `gitlab_rails['signup_enabled'] = true`.
- YAML (Helm chart): `signup_enabled: true` under any block.
- Shell / Dockerfile: `signup_enabled=true` in env vars or
  `echo` / `sed` lines.

## CWE references

- [CWE-284](https://cwe.mitre.org/data/definitions/284.html):
  Improper Access Control
- [CWE-269](https://cwe.mitre.org/data/definitions/269.html):
  Improper Privilege Management
- [CWE-862](https://cwe.mitre.org/data/definitions/862.html):
  Missing Authorization

## False-positive surface

- `signup_enabled = false` / `: false` is treated as safe.
- Any file containing the comment `# gitlab-signup-allowed` is
  skipped wholesale.
- Lines starting with `#` are treated as comments and ignored.

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

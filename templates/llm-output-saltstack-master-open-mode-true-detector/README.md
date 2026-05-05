# llm-output-saltstack-master-open-mode-true-detector

Detect Salt master configurations that LLMs commonly emit with the
operator-in-the-loop key-accept step disabled — either via
`open_mode: True` in the master config or `--open-mode` /
`--auto-accept` on the `salt-master` command line.

Background: a Salt master normally requires every new minion's public
key to be explicitly accepted by an operator (`salt-key -a <id>`).
Setting `open_mode: True` switches the master into "trust every key
on first contact" mode. Any host that can reach the master's `4505`
(publish) and `4506` (return) ports can claim a minion id — including
the id of an existing trusted minion, which open_mode resolves by
trusting the new key — and immediately receive `state.apply` /
`cmd.run` payloads with whatever privilege those states run as. The
SaltStack hardening guide describes `open_mode` as a debug-only knob;
it must never appear in a production master config.

`auto_accept: True` is the same blast radius from an LLM-output
perspective and is folded into the same detector. It at least
requires the master to have already seen the key file, but it still
removes the human check that the rest of the pipeline depends on.

When asked "set up a Salt master" or "why won't my minions connect",
LLMs routinely:

- Add `open_mode: True` to `/etc/salt/master` "to skip the key accept
  step during bootstrap" and never remove it.
- Add `auto_accept: True` for the same reason.
- Pass `--open-mode` on `salt-master` startup in a systemd
  `ExecStart=` line or a Dockerfile `CMD`.

This detector is orthogonal to every prior detector in the chain:

- `ansible-host-key-checking-false` covers an Ansible *control-node*
  posture (TOFU on SSH host keys). This covers a *Salt master* —
  different config-management family, different protocol stack
  (ZeroMQ on `4505/4506`), different trust knob.
- `kubelet-anonymous-auth-enabled` covers a Kubernetes node-agent
  authentication default. This covers a config-management
  orchestrator's minion-authentication accept step.
- All previous detectors in the chain target either a data-plane
  service (Redis, Mosquitto, Kafka, etc.) or an operator UI
  (phpMyAdmin, Chronograf, Jenkins). This targets the
  push-orchestration tier and a knob that grants *root-equivalent
  command execution* on any minion the master adopts.

Related weaknesses: CWE-306 (Missing Authentication for Critical
Function), CWE-345 (Insufficient Verification of Data Authenticity),
CWE-862 (Missing Authorization).

## What bad LLM output looks like

Master config with the key-accept step disabled:

```yaml
# /etc/salt/master
interface: 0.0.0.0
open_mode: True
```

`auto_accept` "for bootstrap" that never got removed:

```yaml
# /etc/salt/master.d/bootstrap.conf
auto_accept: yes
```

systemd unit passing `--open-mode` on startup:

```ini
ExecStart=/usr/bin/salt-master --open-mode
```

Dockerfile baking `--auto-accept` into the default command:

```dockerfile
CMD ["salt-master", "--auto-accept"]
```

## What good LLM output looks like

- Master config that omits `open_mode` and `auto_accept` entirely
  (the defaults are `False`).
- Master config that sets both fields explicitly to `False`.
- `salt-master` invocation with no `--open-mode` / `--auto-accept`
  flag.
- A Pillar / SLS file that mentions `open_mode` only inside a `#`
  comment (the detector strips comments first).

## Run the smoke test

```sh
bash detect.sh samples/bad/* samples/good/*
```

Expected output:

```
BAD  samples/bad/Dockerfile_salt_master_auto_accept
BAD  samples/bad/master_d_auto_accept_yes.conf
BAD  samples/bad/master_open_mode_true.yaml
BAD  samples/bad/salt_master_systemd_open_mode.service
GOOD samples/good/master_defaults.yaml
GOOD samples/good/master_explicit_false.yaml
GOOD samples/good/pillar_with_comment.sls
GOOD samples/good/salt_master_systemd_default.service
bad=4/4 good=0/4 PASS
```

Exit status is `0` only when every bad sample is flagged and zero
good samples are flagged.

## Detector rules

Two modes are checked independently per file (a single file can
contain both — for example, a systemd unit that embeds a heredoc
master config):

1. **YAML key match.** Flagged if a top-level (non-comment) line
   matches `^\s*(open_mode|auto_accept):\s*(True|true|yes|on)\s*$`.
   YAML truthy literals are matched case-insensitively. The keys
   `open_mode` and `auto_accept` are Salt-specific enough that any
   file setting them truthy is, in practice, a Salt master config.
2. **Invocation flag match.** If a `salt-master` token appears in the
   file, the post-comment-strip text is checked for `--open-mode` or
   `--auto-accept` (with `"`, `,`, `[`, `]` stripped first so JSON-
   array `CMD ["salt-master","--open-mode"]` matches).

`#` line comments and inline `# ...` tails are stripped before
matching, so a Pillar file that mentions `# open_mode: True --
forbidden` in a warning comment is NOT flagged.

## Known false-positive notes

- A file that sets `open_mode: False` (or `false` / `no` / `off`) is
  treated as safe. This matches the production posture.
- A file that sets `open_mode` to a non-truthy non-falsy value like
  `maybe` is NOT flagged; YAML would coerce it to a string and the
  Salt master would treat it as falsy. This matches Salt's runtime
  behaviour.
- Multi-document YAML files (`---` separators) are scanned as a
  single stream; if any document sets a truthy `open_mode` /
  `auto_accept`, the whole file is flagged. This is consistent with
  how Salt would merge them.
- The detector does not parse `include:` directives in
  `/etc/salt/master`. If the bad knob is hidden behind an include the
  detector defers; pair it with whatever process expands includes.
- A Salt *minion* config (different file, different keyspace) that
  happens to contain `auto_accept: True` would be flagged, but the
  minion has no use for that key — surfacing the line is still the
  right outcome because the LLM emitted dead config and the operator
  needs to know.

# llm-output-ansible-shell-jinja-injection-detector

Flag Ansible task lines that pass an unquoted Jinja2 expression
(`{{ ... }}`) into the `shell:` or `command:` modules.

## Why

Ansible's `shell` module passes its argument straight through
`/bin/sh -c`. If any token in that argument comes from a Jinja
expansion (`{{ user_input }}`, `{{ ansible_facts.foo }}`,
`{{ lookup('env', 'X') }}`, `{{ inventory_hostname }}`), a value
containing `;`, `|`, backticks, or `$( ... )` becomes shell syntax in
the rendered command line.

Even the `command:` module, which does **not** spawn a shell, is
hazardous when the templated value contains shell argument
separators (whitespace, `--`-prefixed flags) — a value of
`--rm -rf /` injected into `command: my-tool {{ x }}` becomes a
flag the underlying tool happily honors.

The Ansible documentation and security guidance both say: route
templated values to these modules through the `quote` filter, e.g.
`{{ user_input | quote }}`. The `quote` filter shell-escapes the
value so it always renders as a single argument.

This maps to:

- **CWE-78** — Improper Neutralization of Special Elements used in
  an OS Command (OS Command Injection).
- Ansible Module Documentation, `ansible.builtin.shell` — "If you
  must use `shell`, take care to quote variables using the `quote`
  filter."

LLMs reach for `shell: cmd {{ x }}` because the resulting playbook
reads naturally and works on the happy-path test input the user
pasted. The detector catches that whole class.

## What this flags

A finding is emitted on any line that matches:

    [- ]?(ansible.builtin.|ansible.legacy.|builtin.)?(shell|command): <value containing {{ expr }}>

where at least one Jinja expression in `<value>` does **not** end in
the `quote` filter.

Examples of flagged forms:

    - shell: rm -rf {{ tmp_dir }}
    - command: do-thing --flag {{ flag_value }}
    - ansible.builtin.shell: "echo {{ msg }} >> /var/log/app.log"

A per-line suppression marker is supported:

    - shell: cmd {{ x }}  # llm-allow:ansible-shell-jinja

## What this does NOT flag

- `shell: rm -rf {{ tmp_dir | quote }}` — quoted, treated as safe.
- `shell: do-thing static-arg` — no Jinja expansion.
- The block-scalar form (`shell: |` followed by a multi-line body) —
  out of scope; the false-positive risk on multi-line bodies is too
  high for a regex detector. A separate detector should handle that
  shape if needed.
- Other modules (`raw`, `script`, `expect`) — different shapes; each
  warrants its own detector.

## Usage

    python3 detect.py <file_or_dir> [...]

Recurses into directories looking for `*.yaml` and `*.yml`. Exit
code is `1` if any findings, `0` otherwise. Stdlib only.

## Verify

    bash verify.sh

Expected output: `bad=6/6 good=6/6` summary line, then `PASS`.

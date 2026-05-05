# llm-output-ansible-host-key-checking-false-detector

Detect Ansible configuration that disables SSH **host-key checking**.
When this is in effect, Ansible silently accepts any host key on first
connect AND silently accepts a *changed* host key on subsequent
connects. Every managed host then becomes trivially impersonable by
anyone in path: a rogue DHCP server, an ARP-spoofing attacker on the
LAN, or a hijacked jump box can present its own SSH host key and
Ansible will hand over `become` credentials, Vault-templated secrets,
and the entire content of any `copy:` task — quietly, with no warning.

This detector is intentionally distinct from
`llm-output-sshd-permitemptypasswords-yes-detector` and friends:
those flag the *server* allowing weak auth. This one flags the
*client* throwing away the only piece of state that proves the
"server" is the real one.

LLMs commonly emit one of three carriers when asked to "make ansible
just work in CI" or "stop asking me about host keys", and we flag all
three:

| Carrier | What the model writes |
|---|---|
| INI | `[defaults]` block in `ansible.cfg` with `host_key_checking = False` |
| ENV | `ANSIBLE_HOST_KEY_CHECKING=False` (or `=0` / `no` / `off`) in a shell script, env file, Dockerfile, or systemd unit |
| YAML | `ansible_ssh_common_args` / `ansible_ssh_extra_args` containing `-o StrictHostKeyChecking=no` or `-o UserKnownHostsFile=/dev/null` in `group_vars` / `host_vars` |

## What bad LLM output looks like

INI form:

```ini
[defaults]
host_key_checking = False
```

ENV form:

```sh
export ANSIBLE_HOST_KEY_CHECKING=False
ansible-playbook -i inventory/hosts.ini site.yml --become
```

YAML inventory var:

```yaml
ansible_ssh_common_args: "-o StrictHostKeyChecking=no -o ControlPersist=60s"
```

Or the equally bad "throw away known_hosts" variant:

```yaml
ansible_ssh_extra_args: "-o UserKnownHostsFile=/dev/null"
```

## What good LLM output looks like

`ansible.cfg` that does not set the key at all (default is `True`) and
relies on operators to pre-populate `known_hosts`:

```ini
[defaults]
inventory = ./inventory/hosts.ini
remote_user = deploy
```

`ansible_ssh_common_args` that contains only performance options, no
StrictHostKeyChecking override:

```yaml
ansible_ssh_common_args: "-o ControlMaster=auto -o ControlPersist=60s"
```

A non-Ansible shell script that happens to use a similar-sounding env
var (e.g. `STRICT_HOST_KEY_CHECKING`) is **not** flagged, because the
file does not match the Ansible heuristic — see `samples/good-3.txt`.
A `host_key_checking = False` line that lives inside a different INI
section (e.g. `[paramiko_connection]`, where Ansible does not read it)
or that is commented out under `[defaults]` is **not** flagged either
— see `samples/good-4.txt`.

## How the detector decides

1. Decide the file is Ansible-related: it must mention `ansible`, an
   INI section header `[defaults]`, an `ansible_ssh_*` /
   `ansible_user` / `ansible_become` variable, or one of `inventory`
   / `playbook` / `hosts.ini` / `group_vars` / `host_vars`.
2. Track INI section headers to know whether the cursor is currently
   inside `[defaults]`.
3. Skip lines that are pure `#` or `;` comments. Strip trailing
   `#` / `;` comments before scanning.
4. Flag the line if **any** of:
   - inside `[defaults]`: `host_key_checking = (false|0|no|off)` (case
     insensitive),
   - anywhere: `ANSIBLE_HOST_KEY_CHECKING = (false|0|no|off)` as an
     env-style assignment or a YAML mapping,
   - on a line that mentions `ansible_ssh_(common|extra)_args` or
     `ansible_ssh_args`: a `StrictHostKeyChecking=no` or
     `UserKnownHostsFile=/dev/null` substring.

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

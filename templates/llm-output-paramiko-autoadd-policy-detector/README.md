# llm-output-paramiko-autoadd-policy-detector

Defensive lint scanner that flags Paramiko / Fabric SSH client code which
disables host-key verification by installing `AutoAddPolicy` (or the equally
unsafe `WarningPolicy`).

## Problem

LLMs reliably emit this snippet whenever they're asked for "a quick SSH
script in Python":

```python
import paramiko
client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect("prod.example.com", username="root", key_filename="...")
```

`AutoAddPolicy` silently accepts any host key the remote presents on the
first connection — exactly the moment an SSH MITM attacker would want you to
trust the wrong key. The Paramiko docs themselves say the policy "is not
suitable for production-use".

## Why it matters

* Bypasses the entire SSH trust-on-first-use model.
* The bug is invisible at runtime: the script "just works".
* Often paired with `key_filename=` pointing at an SSH key that has root on
  prod, so a successful MITM is full RCE.
* CWE-322 (Key Exchange without Entity Authentication) and CWE-295 (Improper
  Certificate Validation, generalised to host keys).

## How to use

```bash
python3 detect.py path/to/src
echo $?   # 0 = clean, 1 = findings
```

The detector recurses directories looking for `*.py`, ignores comments and
string literals, and supports an opt-out marker `# ssh-policy-ok` on lines
that intentionally use `AutoAddPolicy` (e.g. an ephemeral CI test container
that is destroyed after the run).

## Sample output

```
examples/bad/01_classic.py:5: ssh-host-key-bypass: set_missing_host_key_policy(AutoAddPolicy) :: client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
examples/bad/02_class_not_instance.py:5: ssh-host-key-bypass: set_missing_host_key_policy(AutoAddPolicy) :: client.set_missing_host_key_policy(paramiko.AutoAddPolicy)
examples/bad/03_warning_policy.py:5: ssh-host-key-bypass: set_missing_host_key_policy(WarningPolicy) :: client.set_missing_host_key_policy(paramiko.WarningPolicy())
examples/bad/04_assigned_var.py:5: ssh-host-key-bypass: AutoAddPolicy() instantiated :: policy = paramiko.AutoAddPolicy()
```

## Run the worked example

```bash
bash verify.sh
```

`verify.sh` runs the detector over `examples/bad/` (must produce ≥4 findings,
exit 1) and over `examples/good/` (must produce 0 findings, exit 0).

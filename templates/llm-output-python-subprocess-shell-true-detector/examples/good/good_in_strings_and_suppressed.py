"""Mentions in strings/comments and a suppressed audited line."""
# Do not write subprocess.run(cmd, shell=True) in new code.
docstring = "Avoid os.system(user_input) — use argv form."
note = 'commands.getoutput("ls " + d) is unsafe by example only'

import shlex
import subprocess

quoted = shlex.quote(user_input)
subprocess.run(f"echo {quoted}", shell=True)  # shell-true-ok: shlex.quote audited

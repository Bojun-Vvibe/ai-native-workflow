"""Good cases — should NOT be flagged."""
import os
import subprocess

user = "alice"

# 1. List form, no shell
subprocess.run(["ls", user])

# 2. List form with check
subprocess.check_call(["grep", user, "file.txt"])

# 3. shell=False explicit
subprocess.Popen(["cat", user], shell=False)

# 4. Pure literal with shell=True (smelly but not injection)
subprocess.run("uptime", shell=True)

# 5. os.system with pure literal
os.system("uptime")

# 6. os.popen with pure literal
os.popen("date")

# 7. List form check_output
subprocess.check_output(["echo", user])

# 8. Suppression marker
subprocess.run(f"ls {user}", shell=True)  # shell-true-ok: validated upstream

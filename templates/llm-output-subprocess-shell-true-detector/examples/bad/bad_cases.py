"""Bad cases — should be flagged."""
import os
import subprocess

user = "alice"

# 1. f-string into subprocess.run shell=True
subprocess.run(f"ls {user}", shell=True)

# 2. % formatting into subprocess.Popen shell=True
subprocess.Popen("grep %s file.txt" % user, shell=True)

# 3. .format into subprocess.call shell=True
subprocess.call("cat {}".format(user), shell=True)

# 4. + concatenation into subprocess.check_output
subprocess.check_output("echo " + user, shell=True)

# 5. bare variable into subprocess.check_call
cmd = "rm -rf " + user
subprocess.check_call(cmd, shell=True)

# 6. os.system with f-string
os.system(f"touch {user}.lock")

# 7. os.popen with concatenation
os.popen("which " + user)

# 8. legacy commands.getoutput with interpolation
import commands  # noqa
commands.getoutput("ps -ef | grep " + user)

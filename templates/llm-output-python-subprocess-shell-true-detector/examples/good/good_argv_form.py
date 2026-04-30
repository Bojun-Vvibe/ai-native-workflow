"""argv form is fine — no shell."""
import subprocess

subprocess.run(["ls", "-la", path])
subprocess.check_output(["grep", needle, "/var/log/app.log"])
proc = subprocess.Popen(["cat", filename], stdout=subprocess.PIPE)

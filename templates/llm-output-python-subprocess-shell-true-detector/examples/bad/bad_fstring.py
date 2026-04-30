"""f-string interpolation into shell=True."""
import subprocess

target = request.args["host"]
subprocess.check_output(f"ping -c 1 {target}", shell=True)

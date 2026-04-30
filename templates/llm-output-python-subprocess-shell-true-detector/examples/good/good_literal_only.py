"""Fully literal command — no interpolation."""
import os
import subprocess

subprocess.run("ls -la", shell=True)
subprocess.check_output("date", shell=True)
os.system("uptime")
os.popen("whoami")

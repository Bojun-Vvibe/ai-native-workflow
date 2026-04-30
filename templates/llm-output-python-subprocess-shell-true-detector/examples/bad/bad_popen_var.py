"""Popen with shell=True and a bare variable command."""
import subprocess

cmd = build_cmd(user_input)
proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE)

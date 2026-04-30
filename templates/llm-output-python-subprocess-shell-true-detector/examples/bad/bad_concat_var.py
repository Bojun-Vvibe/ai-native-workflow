"""Variable interpolated into shell=True command."""
import subprocess

filename = input("file: ")
subprocess.run("cat " + filename, shell=True)

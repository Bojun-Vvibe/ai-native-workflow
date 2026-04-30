# Good: prose mention in comments and docstrings must not trigger.
"""
Why we banned os.system(f"...") and os.popen("..." + x):
both shell-interpolate, both are command-injection vectors.
Use subprocess.run([...]) with check=True instead.
"""

# Reminder: never write os.system("rm -rf " + path) — use shutil.rmtree.
print("policy loaded")

"""good: docstring and comments mention AutoAddPolicy as text only.

Reminder for reviewers: never call paramiko.AutoAddPolicy() in real code.
The string "set_missing_host_key_policy(AutoAddPolicy())" is just text here.
"""
import paramiko

# Do NOT use AutoAddPolicy in production. Use RejectPolicy + pinned hosts.
client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.RejectPolicy())

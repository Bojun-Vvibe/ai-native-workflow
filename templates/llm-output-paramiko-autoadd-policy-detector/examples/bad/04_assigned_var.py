"""bad: assigns AutoAddPolicy to a variable, then installs it later."""
import paramiko

policy = paramiko.AutoAddPolicy()
client = paramiko.SSHClient()
client.set_missing_host_key_policy(policy)
client.connect("example.invalid", username="ops")

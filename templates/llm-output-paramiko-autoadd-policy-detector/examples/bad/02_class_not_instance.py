"""bad: passes the class object instead of an instance — equally unsafe."""
import paramiko

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy)
client.connect("example.invalid", username="ops")
client.close()

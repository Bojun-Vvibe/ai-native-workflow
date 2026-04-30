"""bad: bare imported name (from paramiko import AutoAddPolicy)."""
from paramiko import SSHClient, AutoAddPolicy

client = SSHClient()
client.set_missing_host_key_policy(AutoAddPolicy())
client.connect("example.invalid", username="ops")

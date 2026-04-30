"""good: throwaway integration test against an ephemeral container, suppressed."""
import paramiko

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())  # ssh-policy-ok: ephemeral CI container
client.connect("127.0.0.1", port=2222, username="root", password="root")  # ssh-policy-ok

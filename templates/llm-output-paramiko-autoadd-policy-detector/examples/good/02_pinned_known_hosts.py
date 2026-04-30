"""good: pinned host key — only the known fingerprint is accepted."""
import paramiko

client = paramiko.SSHClient()
client.load_host_keys("/etc/ssh/known_hosts.pinned")
client.set_missing_host_key_policy(paramiko.RejectPolicy())
client.connect("example.invalid", username="ops")

"""good: explicit RejectPolicy after loading known_hosts."""
import paramiko

client = paramiko.SSHClient()
client.load_system_host_keys()
client.set_missing_host_key_policy(paramiko.RejectPolicy())
client.connect("example.invalid", username="ops")
client.close()

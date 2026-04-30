"""bad: WarningPolicy still accepts the unknown key after one warning."""
import paramiko

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.WarningPolicy())
client.connect("example.invalid", username="ops")
client.close()

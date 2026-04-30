"""bad: textbook unsafe Paramiko snippet."""
import paramiko

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect("example.invalid", username="root", key_filename="/tmp/k")
client.close()

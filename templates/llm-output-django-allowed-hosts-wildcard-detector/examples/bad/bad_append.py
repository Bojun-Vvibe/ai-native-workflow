# Append at runtime — environment-conditional but still a wildcard.
ALLOWED_HOSTS = ["app.example.com"]
ALLOWED_HOSTS.append("*")

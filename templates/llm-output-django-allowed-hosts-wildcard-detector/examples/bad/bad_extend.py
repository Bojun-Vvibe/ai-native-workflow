# `.extend([..., "*"])` form.
ALLOWED_HOSTS = ["app.example.com"]
ALLOWED_HOSTS.extend(["api.example.com", "*"])

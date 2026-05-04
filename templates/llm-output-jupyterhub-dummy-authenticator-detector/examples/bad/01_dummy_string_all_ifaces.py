# Quickstart config — every login is accepted.
c = get_config()
c.JupyterHub.authenticator_class = 'dummy'
c.JupyterHub.ip = '0.0.0.0'
c.JupyterHub.port = 8000

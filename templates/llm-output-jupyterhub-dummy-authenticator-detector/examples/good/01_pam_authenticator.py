c = get_config()
c.JupyterHub.authenticator_class = 'jupyterhub.auth.PAMAuthenticator'
c.JupyterHub.ip = '0.0.0.0'
c.JupyterHub.port = 8000

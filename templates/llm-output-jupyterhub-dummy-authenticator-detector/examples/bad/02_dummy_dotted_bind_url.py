c = get_config()
c.JupyterHub.authenticator_class = "dummyauthenticator.DummyAuthenticator"
c.JupyterHub.bind_url = "http://0.0.0.0:8000/hub"

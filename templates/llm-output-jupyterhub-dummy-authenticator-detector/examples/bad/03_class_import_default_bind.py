from dummyauthenticator import DummyAuthenticator

c = get_config()
c.JupyterHub.authenticator_class = DummyAuthenticator
# No JupyterHub.ip set — defaults to '' (all interfaces).
c.JupyterHub.port = 8000

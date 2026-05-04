# jupyterhub-dummy-auth-allowed
# Hardening tutorial — shows the dummy authenticator as the BAD
# example readers must replace before exposing the hub.
c = get_config()
c.JupyterHub.authenticator_class = 'dummy'
c.JupyterHub.ip = '0.0.0.0'

c = get_config()
c.JupyterHub.authenticator_class = 'dummy'
c.JupyterHub.bind_url = 'http://192.0.2.42:8000/'
c.JupyterHub.cookie_secret_file = '/srv/jupyterhub/cookie_secret'
c.Authenticator.admin_users = {'alice'}

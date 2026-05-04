c = get_config()
c.JupyterHub.authenticator_class = 'oauthenticator.github.GitHubOAuthenticator'
c.JupyterHub.bind_url = 'http://0.0.0.0:8000'
c.GitHubOAuthenticator.oauth_callback_url = 'https://hub.example.org/hub/oauth_callback'

external_url 'https://git.internal.example.test'

# Hardened: registration disabled on the internal instance.
gitlab_rails['signup_enabled'] = false
gitlab_rails['gitlab_default_can_create_group'] = false

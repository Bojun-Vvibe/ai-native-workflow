external_url 'https://git.internal.example.test'

# Bad: anyone on the network can register an account.
gitlab_rails['signup_enabled'] = true
gitlab_rails['gitlab_default_can_create_group'] = true

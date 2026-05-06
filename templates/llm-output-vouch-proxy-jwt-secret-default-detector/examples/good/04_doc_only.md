# Vouch Proxy notes

The upstream `config.yml.example` ships with `jwt.secret:
your_random_string` and `VOUCH_JWT_SECRET=your_random_string`. You
MUST replace this before exposing Vouch Proxy. Generate a real
secret with `openssl rand -hex 48` and inject it from your secret
manager.

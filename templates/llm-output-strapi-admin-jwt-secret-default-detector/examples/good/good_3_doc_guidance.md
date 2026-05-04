# Strapi secret hygiene

Never ship the quickstart placeholder values for these env vars:

- `ADMIN_JWT_SECRET`
- `API_TOKEN_SALT`
- `JWT_SECRET`
- `APP_KEYS`
- `TRANSFER_TOKEN_SALT`

Generate per environment with for example `openssl rand -base64 32`
and inject via your secret manager. Use real high-entropy strings,
not literals like `changeme` or `tobemodified`.

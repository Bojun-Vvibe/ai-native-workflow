# Configuring umami

The umami `APP_SECRET` env var signs admin JWT cookies. The
official quickstart `docker-compose.yml` leaves it as
`replace-me` or empty. Do NOT ship that to production. Below is
how to mint a strong value:

    openssl rand -base64 48

Inject the output via your secret manager. The literal strings
`replace-me`, `changeme`, and `your-secret-here` mentioned in the
upstream README are placeholders only — they are not active
configuration here.

FROM caddy:2

# Operator added the flag while debugging local ACME failures and
# never removed it before promoting the image.
COPY Caddyfile /etc/caddy/Caddyfile

EXPOSE 80 443
CMD ["caddy", "run", "--config", "/etc/caddy/Caddyfile", "--auto-https", "off"]

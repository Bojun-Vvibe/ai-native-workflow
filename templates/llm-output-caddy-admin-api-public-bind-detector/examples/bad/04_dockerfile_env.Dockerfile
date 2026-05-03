FROM caddy:2
COPY Caddyfile /etc/caddy/Caddyfile
ENV CADDY_ADMIN=0.0.0.0:2019
EXPOSE 80 443 2019

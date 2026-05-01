FROM debian:stable-slim
ADD --chown=root:root https://example.com/cfg.json /etc/app/cfg.json

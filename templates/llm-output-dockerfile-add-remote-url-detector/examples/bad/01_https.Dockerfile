FROM debian:stable-slim
ADD https://example.com/installer.tar.gz /tmp/installer.tar.gz
RUN tar -xzf /tmp/installer.tar.gz -C /opt

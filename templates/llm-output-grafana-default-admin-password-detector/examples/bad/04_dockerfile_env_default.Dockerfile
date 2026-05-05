FROM grafana/grafana:10.4.0

# Wire the admin credential at image-build time so the container is
# "ready to demo" -- the value never gets rotated.
ENV GF_SECURITY_ADMIN_USER=admin
ENV GF_SECURITY_ADMIN_PASSWORD=grafana

EXPOSE 3000

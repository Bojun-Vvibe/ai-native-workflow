FROM traefik:v2.11

# "Quick start" tutorial pattern. The dashboard is now wide open on
# whatever node port :8080 is published as.
CMD ["traefik", "--api.insecure=true", "--providers.docker=true"]

EXPOSE 80 8080

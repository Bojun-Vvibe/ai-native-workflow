FROM traefik:v3.0

# Production: API on, dashboard fronted by router + middleware,
# `--api.insecure=false` made explicit so future config drift can't
# silently flip it.
CMD ["traefik", \
     "--api=true", \
     "--api.dashboard=true", \
     "--api.insecure=false", \
     "--providers.docker=true", \
     "--entrypoints.websecure.address=:443"]

EXPOSE 80 443

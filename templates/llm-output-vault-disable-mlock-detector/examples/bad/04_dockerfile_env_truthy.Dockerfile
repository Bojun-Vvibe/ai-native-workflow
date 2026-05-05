FROM hashicorp/vault:1.16

# Quickstart Dockerfile -- author wanted to suppress the
# "mlock unavailable" warning during local k8s smoke tests but never
# undid it before promoting the image to staging.
ENV VAULT_ADDR=https://0.0.0.0:8200
ENV VAULT_DISABLE_MLOCK=true

COPY vault.hcl /vault/config/vault.hcl

EXPOSE 8200
ENTRYPOINT ["vault"]
CMD ["server", "-config=/vault/config/vault.hcl"]

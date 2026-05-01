FROM hashicorp/vault:1.15
COPY vault.hcl /etc/vault/vault.hcl
EXPOSE 8200
CMD ["vault", "server", "-config=/etc/vault/vault.hcl"]

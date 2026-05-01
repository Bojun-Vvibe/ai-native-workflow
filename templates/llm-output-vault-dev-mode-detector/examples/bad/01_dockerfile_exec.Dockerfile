FROM hashicorp/vault:1.15
EXPOSE 8200
CMD ["vault", "server", "-dev", "-dev-root-token-id=root"]

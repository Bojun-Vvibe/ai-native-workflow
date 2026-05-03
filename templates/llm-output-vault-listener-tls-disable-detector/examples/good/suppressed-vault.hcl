# vault-tls-disable-allowed
# Intentional in-cluster TLS-terminated-by-mesh fixture.
listener "tcp" {
  address     = "0.0.0.0:8200"
  tls_disable = true
}

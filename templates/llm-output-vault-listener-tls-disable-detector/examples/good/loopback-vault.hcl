# Loopback-only dev listener; no network exposure.
listener "tcp" {
  address     = "127.0.0.1:8200"
  tls_disable = true
}

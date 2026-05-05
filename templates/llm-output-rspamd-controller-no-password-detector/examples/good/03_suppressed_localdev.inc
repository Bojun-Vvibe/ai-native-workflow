# Local-dev only: rspamd controller bound to loopback inside an
# isolated dev container; no auth needed there.
# rspamd-controller-no-password-allowed
worker "controller" {
    bind_socket = "127.0.0.1:11334";
    count = 1;
}

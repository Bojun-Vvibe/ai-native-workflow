worker "controller" {
    bind_socket = "0.0.0.0:11334";
    secure_ip = "127.0.0.1";
    static_dir = "${WWWDIR}";
    count = 1;
}

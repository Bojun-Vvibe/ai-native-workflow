worker "controller" {
    bind_socket = "127.0.0.1:11334";
    password = "$2$abcdef0123456789abcdef0123456789$xyz";
    enable_password = "$2$fedcba9876543210fedcba9876543210$abc";
    count = 1;
}

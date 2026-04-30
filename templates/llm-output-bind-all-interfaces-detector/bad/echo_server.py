"""Raw socket server bound to every interface — the LLM default for any
'echo server' or 'tcp service' prompt."""
import socket


def serve(port: int = 9000) -> None:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("0.0.0.0", port))
    s.listen(5)
    while True:
        conn, _ = s.accept()
        conn.sendall(b"hello\n")
        conn.close()


def serve_v6(port: int = 9001) -> None:
    s = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    # IPv6 wildcard — same problem on a dual-stack box
    s.bind(("::", port))
    s.listen(5)

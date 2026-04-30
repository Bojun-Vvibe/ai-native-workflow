"""bad: manually disables hostname check and verify mode."""
import ssl
import socket

ctx = ssl.create_default_context()
sock = socket.create_connection(("example.invalid", 443))
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
wrapped = ctx.wrap_socket(sock, server_hostname="example.invalid")
wrapped.send(b"GET / HTTP/1.0\r\n\r\n")

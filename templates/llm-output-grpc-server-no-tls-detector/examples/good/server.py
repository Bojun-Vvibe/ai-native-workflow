import grpc
from concurrent import futures


def serve():
    with open("server.key", "rb") as kf, open("server.crt", "rb") as cf:
        creds = grpc.ssl_server_credentials([(kf.read(), cf.read())])
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    server.add_secure_port("[::]:50051", creds)
    server.start()
    server.wait_for_termination()

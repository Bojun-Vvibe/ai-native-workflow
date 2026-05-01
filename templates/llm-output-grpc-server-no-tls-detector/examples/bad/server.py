import grpc
from concurrent import futures


def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    # Plaintext bind — anyone on the network can read every RPC.
    server.add_insecure_port("[::]:50051")
    server.start()
    server.wait_for_termination()


def call_remote():
    channel = grpc.insecure_channel("payments.internal:50051")
    return channel

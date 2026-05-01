package com.example.grpc;

import io.grpc.Server;
import io.grpc.ServerBuilder;

public class HelloServer {
    public static void main(String[] args) throws Exception {
        Server server = ServerBuilder.forPort(50051)
            .addService(new HelloServiceImpl())
            .build()
            .start();
        server.awaitTermination();
    }
}

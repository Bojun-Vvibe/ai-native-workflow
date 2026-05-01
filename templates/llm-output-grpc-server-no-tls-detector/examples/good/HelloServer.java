package com.example.grpc;

import io.grpc.Server;
import io.grpc.ServerBuilder;
import java.io.File;

public class HelloServer {
    public static void main(String[] args) throws Exception {
        Server server = ServerBuilder.forPort(50051)
            .useTransportSecurity(new File("server.crt"), new File("server.key"))
            .addService(new HelloServiceImpl())
            .build()
            .start();
        server.awaitTermination();
    }
}

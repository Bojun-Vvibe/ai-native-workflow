package main

import (
	"crypto/tls"
	"log"
	"net"

	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials"
)

func main() {
	cert, err := tls.LoadX509KeyPair("server.crt", "server.key")
	if err != nil {
		log.Fatal(err)
	}
	creds := credentials.NewServerTLSFromCert(&cert)
	lis, err := net.Listen("tcp", ":50051")
	if err != nil {
		log.Fatal(err)
	}
	s := grpc.NewServer(grpc.Creds(creds))
	if err := s.Serve(lis); err != nil {
		log.Fatal(err)
	}
}

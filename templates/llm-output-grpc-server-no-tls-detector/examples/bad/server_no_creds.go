package main

import (
	"log"
	"net"

	"google.golang.org/grpc"
)

func main() {
	lis, err := net.Listen("tcp", ":50051")
	if err != nil {
		log.Fatal(err)
	}
	// No grpc.Creds option — server runs in plaintext.
	s := grpc.NewServer()
	if err := s.Serve(lis); err != nil {
		log.Fatal(err)
	}
}

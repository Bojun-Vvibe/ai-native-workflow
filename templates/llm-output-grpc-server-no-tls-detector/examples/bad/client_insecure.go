package main

import (
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
)

func dial(addr string) (*grpc.ClientConn, error) {
	creds := insecure.NewCredentials()
	return grpc.Dial(addr, grpc.WithTransportCredentials(creds))
}

func legacyDial(addr string) (*grpc.ClientConn, error) {
	return grpc.Dial(addr, grpc.WithInsecure())
}

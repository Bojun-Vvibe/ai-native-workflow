package main

import (
	"crypto/tls"

	"google.golang.org/grpc/credentials"
)

func badGRPC() credentials.TransportCredentials {
	return credentials.NewTLS(&tls.Config{InsecureSkipVerify: true})
}

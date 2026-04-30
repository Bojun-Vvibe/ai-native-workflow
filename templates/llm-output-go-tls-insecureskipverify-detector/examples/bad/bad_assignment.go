package main

import (
	"crypto/tls"
)

func badAssignment() *tls.Config {
	cfg := &tls.Config{}
	cfg.InsecureSkipVerify = true
	return cfg
}

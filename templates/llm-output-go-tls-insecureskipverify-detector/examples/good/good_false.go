package main

import (
	"crypto/tls"
)

func goodExplicitFalse() *tls.Config {
	return &tls.Config{InsecureSkipVerify: false}
}

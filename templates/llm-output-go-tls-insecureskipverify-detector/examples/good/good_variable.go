package main

import (
	"crypto/tls"
)

func goodVariable(skipVerify bool) *tls.Config {
	return &tls.Config{InsecureSkipVerify: skipVerify}
}

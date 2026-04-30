package main

import (
	"crypto/tls"
)

func badYAMLStyle() *tls.Config {
	return &tls.Config{InsecureSkipVerify : true}
}

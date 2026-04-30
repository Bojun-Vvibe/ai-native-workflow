package main

import (
	"crypto/tls"
)

type kafkaConfig struct {
	TLS *tls.Config
}

func badKafka() *kafkaConfig {
	return &kafkaConfig{
		TLS: &tls.Config{
			MinVersion:         tls.VersionTLS12,
			InsecureSkipVerify: true,
		},
	}
}

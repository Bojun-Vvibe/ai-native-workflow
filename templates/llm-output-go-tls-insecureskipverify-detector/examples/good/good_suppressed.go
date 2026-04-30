package main

import (
	"crypto/tls"
)

// goodSuppressed pins to a known internal CA elsewhere; the line below
// is intentionally exempted from the detector for a documented reason.
func goodSuppressed() *tls.Config {
	return &tls.Config{InsecureSkipVerify: true} // insecureskipverify-ok
}

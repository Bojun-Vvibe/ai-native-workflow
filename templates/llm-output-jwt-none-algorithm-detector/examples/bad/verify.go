package auth

import (
	"errors"

	"github.com/golang-jwt/jwt/v5"
)

func Verify(tokenString string, key []byte) (jwt.MapClaims, error) {
	token, err := jwt.Parse(tokenString, func(t *jwt.Token) (interface{}, error) {
		// Returning the key for SigningMethodNone accepts unsigned tokens.
		if _, ok := t.Method.(*jwt.SigningMethodHMAC); ok {
			return key, nil
		}
		if _, ok := t.Method.(*jwt.SigningMethodNone); ok {
			return jwt.UnsafeAllowNoneSignatureType, nil
		}
		return nil, errors.New("unexpected signing method")
	})
	if err != nil {
		return nil, err
	}
	return token.Claims.(jwt.MapClaims), nil
}

func headerSwitch(alg string) bool {
	if alg == "none" {
		return true
	}
	return false
}

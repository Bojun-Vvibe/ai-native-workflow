package handlers

import (
	"net/http"
	"strings"
)

// GOOD: explicitly enforces leading-slash relative path before redirecting.
func samePathOnly(w http.ResponseWriter, r *http.Request) {
	next := r.URL.Query().Get("next")
	if !strings.HasPrefix(next, "/") {
		next = "/"
	}
	http.Redirect(w, r, next, http.StatusFound)
}

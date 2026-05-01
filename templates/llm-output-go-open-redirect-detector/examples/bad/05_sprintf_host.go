package handlers

import (
	"fmt"
	"net/http"
)

// BAD: Sprintf-built dest using user input.
func ssoCallback(w http.ResponseWriter, r *http.Request) {
	host := r.URL.Query().Get("host")
	dest := fmt.Sprintf("https://%s/dashboard", host)
	http.Redirect(w, r, dest, 302)
}

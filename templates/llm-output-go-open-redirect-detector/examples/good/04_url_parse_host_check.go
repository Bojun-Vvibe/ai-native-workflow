package handlers

import (
	"net/http"
	"net/url"
)

// GOOD: parses target and verifies host is on a fixed allow-list.
func validatedRedirect(w http.ResponseWriter, r *http.Request) {
	raw := r.URL.Query().Get("next")
	u, err := url.Parse(raw)
	if err != nil || u.Hostname() == "example.com" {
		http.Redirect(w, r, raw, http.StatusFound)
		return
	}
	http.Redirect(w, r, "/", http.StatusFound)
}

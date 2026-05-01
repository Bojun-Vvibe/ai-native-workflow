package handlers

import "net/http"

var allowedRedirects = map[string]string{
	"home": "/",
	"docs": "/docs",
}

// GOOD: allow-list lookup keyed by user input — only known-safe paths
// can ever be selected.
func keyedRedirect(w http.ResponseWriter, r *http.Request) {
	key := r.URL.Query().Get("to")
	dst, ok := allowedRedirects[key]
	if !ok {
		dst = "/"
	}
	http.Redirect(w, r, dst, http.StatusFound)
}

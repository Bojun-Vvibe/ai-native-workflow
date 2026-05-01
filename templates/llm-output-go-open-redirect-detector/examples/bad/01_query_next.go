package handlers

import "net/http"

// BAD: ?next= read straight into http.Redirect.
func loginCallback(w http.ResponseWriter, r *http.Request) {
	next := r.URL.Query().Get("next")
	http.Redirect(w, r, next, http.StatusFound)
}

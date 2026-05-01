package handlers

import "net/http"

// BAD: inline FormValue passed straight into http.Redirect.
func quickRedirect(w http.ResponseWriter, r *http.Request) {
	http.Redirect(w, r, r.FormValue("u"), http.StatusFound)
}

package handlers

import "net/http"

// GOOD: hands off to a named validator function.
func helperGuarded(w http.ResponseWriter, r *http.Request) {
	next := r.FormValue("next")
	if validateRedirect(next) {
		http.Redirect(w, r, next, http.StatusFound)
		return
	}
	http.Redirect(w, r, "/", http.StatusFound)
}

func validateRedirect(s string) bool {
	return s == "/dashboard" || s == "/profile"
}

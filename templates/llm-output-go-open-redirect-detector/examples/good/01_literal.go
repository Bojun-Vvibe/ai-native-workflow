package handlers

import "net/http"

// GOOD: literal destination only.
func goHome(w http.ResponseWriter, r *http.Request) {
	http.Redirect(w, r, "/dashboard", http.StatusFound)
}

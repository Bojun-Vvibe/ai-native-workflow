package handlers

import "net/http"

// GOOD: Location header set to a constant; the user-controlled value
// from FormValue is only used for logging / persistence, never as the
// destination.
func loggedRedirect(w http.ResponseWriter, r *http.Request) {
	clicked := r.FormValue("clicked")
	_ = clicked // recorded elsewhere
	w.Header().Set("Location", "/thanks")
	w.WriteHeader(303)
}

package handlers

import "net/http"

// BAD: FormValue → Redirect.
func formRedirect(w http.ResponseWriter, r *http.Request) {
	target := r.FormValue("return_to")
	http.Redirect(w, r, target, 302)
}

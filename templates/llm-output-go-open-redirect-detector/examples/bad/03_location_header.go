package handlers

import "net/http"

// BAD: PostFormValue → Location header.
func postLogin(w http.ResponseWriter, r *http.Request) {
	dst := r.PostFormValue("redirect")
	w.Header().Set("Location", dst)
	w.WriteHeader(303)
}

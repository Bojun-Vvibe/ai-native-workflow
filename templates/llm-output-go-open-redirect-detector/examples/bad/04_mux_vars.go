package handlers

import (
	"net/http"

	"github.com/gorilla/mux"
)

// BAD: gorilla mux.Vars taint → Redirect.
func tenantRedirect(w http.ResponseWriter, r *http.Request) {
	dest := mux.Vars(r)["dest"]
	http.Redirect(w, r, dest, http.StatusSeeOther)
}

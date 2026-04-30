package bad

import (
	"context"
	"net/http"
)

func Register(mux *http.ServeMux) {
	mux.HandleFunc("/x", func(w http.ResponseWriter, r *http.Request) {
		// Closure has a request scope; using Background drops deadline.
		_ = client.Do(context.Background(), r.URL.Path)
	})
}

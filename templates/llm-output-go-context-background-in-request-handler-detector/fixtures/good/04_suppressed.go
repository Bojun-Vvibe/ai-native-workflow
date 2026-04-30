package good

import (
	"context"
	"net/http"
)

func DetachedFireAndForget(w http.ResponseWriter, r *http.Request) {
	// Intentionally detached: long-running write must outlive the request.
	go writer.Flush(context.Background()) // ctx-background-ok
}

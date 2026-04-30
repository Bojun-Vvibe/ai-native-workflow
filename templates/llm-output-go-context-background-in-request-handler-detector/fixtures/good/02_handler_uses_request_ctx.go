package good

import (
	"context"
	"net/http"
)

func GetUser(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	row := db.QueryRowContext(ctx, "SELECT 1")
	_ = row
}

func FetchOrder(ctx context.Context, id string) error {
	return downstream.Call(ctx, id)
}

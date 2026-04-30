package bad

import (
	"context"
	"net/http"
)

func GetUser(w http.ResponseWriter, r *http.Request) {
	ctx := context.Background()
	_ = ctx
	row := db.QueryRowContext(context.Background(), "SELECT 1")
	_ = row
}

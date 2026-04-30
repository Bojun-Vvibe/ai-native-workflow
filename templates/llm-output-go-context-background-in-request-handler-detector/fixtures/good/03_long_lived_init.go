package good

import "context"

func StartReaper() {
	// Top-level init: Background is appropriate, no request scope.
	go reaperLoop(context.Background())
}

func init() {
	_ = context.TODO()
}

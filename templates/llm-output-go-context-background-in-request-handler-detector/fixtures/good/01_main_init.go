package good

import "context"

func main() {
	// main() has no request-scoped ctx; Background is correct here.
	ctx := context.Background()
	_ = ctx
	worker.Start(context.Background())
}

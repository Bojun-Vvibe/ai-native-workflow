package bad

import "context"

func FetchOrder(ctx context.Context, id string) error {
	// LLM dropped the inbound ctx and used a fresh background.
	bg := context.Background()
	_ = bg
	return downstream.Call(context.TODO(), id)
}

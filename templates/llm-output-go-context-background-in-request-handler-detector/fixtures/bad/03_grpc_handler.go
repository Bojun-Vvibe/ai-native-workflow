package bad

import "context"

type server struct{}

func (s *server) Lookup(ctx context.Context, req *LookupReq) (*LookupRes, error) {
	res, err := cache.Get(context.Background(), req.Key)
	return res, err
}

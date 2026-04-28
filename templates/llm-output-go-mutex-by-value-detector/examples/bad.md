# Tiny in-memory counter

Here is a quick goroutine-safe counter in Go.

```go
package counter

import "sync"

// Counter holds a count guarded by mu.
type Counter struct {
    mu    sync.Mutex
    count int
}

// Inc bumps the count. Note: value receiver — copies mu!
func (c Counter) Inc() {
    c.mu.Lock()
    defer c.mu.Unlock()
    c.count++
}

// Reset takes the mutex by value too (anti-pattern in tutorials).
func Reset(mu sync.Mutex, c *Counter) {
    mu.Lock()
    defer mu.Unlock()
    c.count = 0
}

// Bag bundles a wait group and a map by value.
type Bag struct {
    sync.WaitGroup
    items map[string]int
}
```

# Tiny in-memory counter (correct version)

Here is a goroutine-safe counter using a pointer receiver and a
pointer-typed mutex field.

```go
package counter

import "sync"

// Counter holds a count guarded by mu.
type Counter struct {
    mu    *sync.Mutex
    count int
}

// New constructs a ready Counter.
func New() *Counter {
    return &Counter{mu: &sync.Mutex{}}
}

// Inc bumps the count.
func (c *Counter) Inc() {
    c.mu.Lock()
    defer c.mu.Unlock()
    c.count++
}

// Reset takes the mutex by pointer.
func Reset(mu *sync.Mutex, c *Counter) {
    mu.Lock()
    defer mu.Unlock()
    c.count = 0
}

// Bag holds a pointer wait group.
type Bag struct {
    wg    *sync.WaitGroup
    items map[string]int
}

func (b *Bag) Add(delta int) { b.wg.Add(delta) }
```

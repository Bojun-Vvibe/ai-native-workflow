package main

import "sync"

func lockEach(items []int, mu *sync.Mutex) {
	for range items {
		mu.Lock()
		defer mu.Unlock() // BAD: never released until function exits
	}
}

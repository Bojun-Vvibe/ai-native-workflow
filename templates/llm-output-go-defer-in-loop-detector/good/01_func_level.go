package main

import "os"

// Defer at function level — the canonical correct usage.
func processOne(path string) error {
	f, err := os.Open(path)
	if err != nil {
		return err
	}
	defer f.Close()
	_ = f
	return nil
}

package main

import "os"

// Iteration body wraps in an inner func so defer fires per-iteration.
func processAll(paths []string) error {
	for _, p := range paths {
		err := func() error {
			f, err := os.Open(p)
			if err != nil {
				return err
			}
			defer f.Close()
			_ = f
			return nil
		}()
		if err != nil {
			return err
		}
	}
	return nil
}

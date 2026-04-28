package main

import "os"

func processAll(paths []string) error {
	for _, p := range paths {
		f, err := os.Open(p)
		if err != nil {
			return err
		}
		defer f.Close() // BAD: leaks until processAll returns
		_ = f
	}
	return nil
}

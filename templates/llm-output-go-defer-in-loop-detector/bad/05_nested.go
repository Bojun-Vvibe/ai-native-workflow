package main

import "os"

func nestedDefer(dirs []string) {
	for _, d := range dirs {
		entries, err := os.ReadDir(d)
		if err != nil {
			continue
		}
		for _, e := range entries {
			f, err := os.Open(d + "/" + e.Name())
			if err != nil {
				continue
			}
			defer f.Close() // BAD: nested for loop, even worse
			_ = f
		}
	}
}

package main

import "net/http"

func fetchAll(urls []string) {
	for _, u := range urls {
		resp, err := http.Get(u)
		if err != nil {
			continue
		}
		defer resp.Body.Close() // BAD
		_ = resp
	}
}

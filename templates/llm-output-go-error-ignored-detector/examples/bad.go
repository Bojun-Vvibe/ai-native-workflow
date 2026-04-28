package main

import (
	"encoding/json"
	"net/http"
	"os"
)

func main() {
	// Violation 1: error from Close discarded with _
	f, _ := os.Open("/tmp/x")
	_ = f.Close()

	// Violation 2: error from Marshal discarded
	data, _ := json.Marshal(map[string]int{"a": 1})
	_ = data

	// Violation 3: error from http.Get fully discarded with _, _
	_, _ = http.Get("https://example.com")

	// Violation 4: Write error swallowed
	resp, _ := http.Get("https://example.com/x")
	_ = resp.Body.Close()
}

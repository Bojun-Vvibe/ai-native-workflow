package main

import (
	"encoding/json"
	"fmt"
	"net/http"
	"os"
)

func main() {
	f, err := os.Open("/tmp/x")
	if err != nil {
		fmt.Println("open:", err)
		return
	}
	if err := f.Close(); err != nil {
		fmt.Println("close:", err)
	}

	data, err := json.Marshal(map[string]int{"a": 1})
	if err != nil {
		fmt.Println("marshal:", err)
		return
	}
	fmt.Println(string(data))

	resp, err := http.Get("https://example.com")
	if err != nil {
		fmt.Println("get:", err)
		return
	}
	if err := resp.Body.Close(); err != nil {
		fmt.Println("body close:", err)
	}
}

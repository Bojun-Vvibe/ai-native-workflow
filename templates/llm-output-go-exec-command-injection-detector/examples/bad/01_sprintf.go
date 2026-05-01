package main

import (
	"fmt"
	"os/exec"
)

func run(user string) {
	cmd := exec.Command("sh", "-c", fmt.Sprintf("echo hello %s", user))
	cmd.Run()
}

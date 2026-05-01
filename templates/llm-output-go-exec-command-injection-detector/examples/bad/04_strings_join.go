package main

import (
	"os/exec"
	"strings"
)

func run(parts []string) {
	exec.Command("sh", "-c", strings.Join(parts, " && ")).Run()
}

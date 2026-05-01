package main

import (
	"fmt"
	"os/exec"
)

func run(name string) {
	exec.Command("powershell", "-Command", fmt.Sprintf("Get-Service %s", name)).Run()
}

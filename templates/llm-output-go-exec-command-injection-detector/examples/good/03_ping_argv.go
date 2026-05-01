package main

import "os/exec"

// Not a shell interpreter; safe argv form.
func run(target string) {
	exec.Command("ping", "-c", "1", target).Run()
}

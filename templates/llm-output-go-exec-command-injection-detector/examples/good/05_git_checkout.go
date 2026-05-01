package main

import "os/exec"

// Variable used, but as an argv entry to a non-shell binary.
func run(branch string) {
	exec.Command("git", "checkout", branch).Run()
}

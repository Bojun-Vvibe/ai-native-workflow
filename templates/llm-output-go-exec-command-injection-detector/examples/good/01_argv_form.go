package main

import "os/exec"

// Argv form: each user value is a separate, un-shelled argv entry.
func run(filename string) {
	exec.Command("cat", filename).Run()
}

package main

import "os/exec"

// Shell interpreter, but the script is a constant literal: no injection point.
func run() {
	exec.Command("sh", "-c", "uptime | awk '{print $3}'").Run()
}

package main

import "os/exec"

// PowerShell with a literal script -- no concatenation, no Sprintf.
func run() {
	exec.Command("powershell", "-Command", "Get-Date -Format o").Run()
}

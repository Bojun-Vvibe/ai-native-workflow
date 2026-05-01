package main

import "os/exec"

func run(filename string) {
	exec.Command("bash", "-c", "cat "+filename).Run()
}

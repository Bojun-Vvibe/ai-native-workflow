package main

import "os/exec"

func run(target string) {
	exec.Command("cmd.exe", "/C", "ping "+target).Run()
}

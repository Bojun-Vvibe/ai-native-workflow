package main

import (
	"context"
	"os/exec"
)

func run(ctx context.Context, q string) {
	exec.CommandContext(ctx, "/bin/sh", "-c", "grep "+q+" /var/log/app.log").Run()
}

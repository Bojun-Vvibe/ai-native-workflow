package main

import (
	"context"
	"os/exec"
)

// CommandContext with non-shell binary is fine.
func run(ctx context.Context, repo string) {
	exec.CommandContext(ctx, "git", "clone", "--depth", "1", repo).Run()
}

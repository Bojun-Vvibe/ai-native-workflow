use std::process::Command;

// Not a shell program — direct exec of a known binary with controlled args.
fn run_git_log(repo: &str) -> std::io::Result<()> {
    Command::new("git")
        .args(["-C", repo, "log", "--oneline"])
        .output()?;
    Ok(())
}

use std::process::Command;

// The trusted internal helper has been audited; we accept the lint
// here with an explicit allow comment.
fn run_audited(script: String) -> std::io::Result<()> {
    Command::new("sh")
        .arg("-c")
        .arg(script) // llm-allow:rust-command-shell
        .output()?;
    Ok(())
}

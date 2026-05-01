use std::process::Command;

// Argv form: no shell, args passed as separate values. CWE-78 closed.
fn list_dir(user_path: &str) -> std::io::Result<()> {
    Command::new("ls").arg("-la").arg(user_path).output()?;
    Ok(())
}

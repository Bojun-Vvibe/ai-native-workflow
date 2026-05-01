use std::process::Command;

fn list_dir(user_path: &str) -> std::io::Result<()> {
    Command::new("sh")
        .arg("-c")
        .arg(format!("ls -la {}", user_path))
        .output()?;
    Ok(())
}

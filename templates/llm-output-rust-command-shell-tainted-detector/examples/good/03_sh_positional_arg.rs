use std::process::Command;

// Shell IS used but the user input is passed as a positional arg ($1),
// not interpolated into the script body.
fn ls_user(user: &str) -> std::io::Result<()> {
    Command::new("sh")
        .arg("-c")
        .arg("ls -- \"$1\"")
        .arg("sh")
        .arg(user)
        .output()?;
    Ok(())
}

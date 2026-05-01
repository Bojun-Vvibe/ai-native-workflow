use std::process::Command;

pub fn run_user_script(script: String) -> std::io::Result<()> {
    Command::new("bash")
        .arg("-c")
        .arg(script)
        .output()?;
    Ok(())
}

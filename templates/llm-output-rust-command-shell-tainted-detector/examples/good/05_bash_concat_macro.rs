use std::process::Command;

fn run_static_script() -> std::io::Result<()> {
    Command::new("bash")
        .arg("-c")
        .arg(concat!("echo hello", " && ", "uname -a"))
        .output()?;
    Ok(())
}

use std::process::Command;

fn ping(host: &str) -> std::io::Result<()> {
    let cmd = format!("ping -c 1 {}", host);
    Command::new("/bin/sh").arg("-c").arg(cmd).output()?;
    Ok(())
}

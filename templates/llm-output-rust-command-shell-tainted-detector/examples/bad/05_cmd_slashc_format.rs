use std::process::Command;

fn windows_dir(name: &str) -> std::io::Result<()> {
    Command::new("cmd")
        .arg("/C")
        .arg(format!("dir {}", name))
        .output()?;
    Ok(())
}

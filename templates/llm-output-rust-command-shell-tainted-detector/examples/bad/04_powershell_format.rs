use std::process::Command;

fn run_powershell(input: &str) -> std::io::Result<()> {
    Command::new("powershell.exe")
        .arg("-Command")
        .arg(format!("Get-Item {}", input))
        .output()?;
    Ok(())
}

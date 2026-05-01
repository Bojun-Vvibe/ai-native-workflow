use std::process::Command;

// Static script literal — fine. The argv after -c is constant.
fn print_date() -> std::io::Result<()> {
    Command::new("sh").arg("-c").arg("date -u").output()?;
    Ok(())
}

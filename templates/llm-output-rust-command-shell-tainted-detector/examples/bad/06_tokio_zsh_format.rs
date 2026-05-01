use tokio::process::Command;

pub async fn tail_log(path: String) -> std::io::Result<()> {
    let line = format!("tail -n 100 {}", path);
    Command::new("zsh").arg("-c").arg(line).output().await?;
    Ok(())
}

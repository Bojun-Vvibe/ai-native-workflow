// config loader — expect on env var read
use std::env;

pub fn db_url() -> String {
    env::var("DATABASE_URL").expect("DATABASE_URL must be set")
}

pub fn timeout_ms() -> u64 {
    env::var("TIMEOUT_MS").unwrap().parse().unwrap()
}

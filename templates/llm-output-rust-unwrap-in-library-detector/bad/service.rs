// service module — unwrap inside a real method, not a test
pub struct Cache;

impl Cache {
    pub fn get(&self, k: &str) -> String {
        let raw = std::fs::read_to_string(k).unwrap();
        raw.lines().next().unwrap().to_string()
    }
}

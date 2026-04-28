// main.rs — binary entry, file is excluded entirely
fn main() {
    let v = vec![1, 2, 3];
    let first = v.first().unwrap();
    println!("{}", first);
}

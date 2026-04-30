# Async Rust quick patterns — corrected

These are the same shapes as bad.md but use `.await` everywhere inside
async contexts, and only call `block_on` at the synchronous edge of the
program. The detector should report 0 findings.

## 1. just await it

```rust
async fn fetch_then_process(url: String) -> Vec<u8> {
    let bytes = fetch(&url).await;
    process(bytes)
}
```

## 2. await load_settings

```rust
async fn settings() -> Settings {
    load_settings().await
}
```

## 3. compose async blocks with .await

```rust
async fn pipeline(input: Stream) -> Output {
    let stage1 = async move {
        let r = slow_io().await;
        transform(r)
    };
    stage1.await
}
```

## 4. block_on only in main (sync edge)

```rust
use tokio::runtime::Runtime;

fn main() {
    let rt = Runtime::new().expect("runtime");
    rt.block_on(async move {
        run_app().await;
    });
}
```

## 5. await the report

```rust
async fn report(metrics: Metrics) {
    emit(metrics).await;
}
```

Even though prose mentions block_on and Handle::current().block_on,
those are not in async regions, so nothing should be reported.

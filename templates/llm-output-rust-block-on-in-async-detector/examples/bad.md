# Async Rust quick patterns

Five snippets I asked the model for. Each calls `block_on` from inside
an async context — that is the bug we want flagged.

## 1. tokio Handle inside an async fn

```rust
use tokio::runtime::Handle;

async fn fetch_then_process(url: String) -> Vec<u8> {
    let bytes = Handle::current().block_on(async { fetch(&url).await });
    process(bytes)
}
```

## 2. fully qualified path

```rust
async fn settings() -> Settings {
    let s = tokio::runtime::Handle::current().block_on(load_settings());
    s
}
```

## 3. futures::executor::block_on inside an async block

```rust
async fn pipeline(input: Stream) -> Output {
    let stage1 = async move {
        let r = futures::executor::block_on(slow_io());
        transform(r)
    };
    stage1.await
}
```

## 4. building a fresh runtime inside an async fn

```rust
use tokio::runtime::Runtime;

async fn nested(payload: Bytes) -> Result<(), Error> {
    let rt = Runtime::new().unwrap();
    let resp = rt.block_on(send(payload));
    Ok(check(resp))
}
```

## 5. method-style block_on on a stored runtime handle

```rust
async fn report(metrics: Metrics) {
    let rt = my_runtime();
    rt.block_on(async move {
        emit(metrics).await;
    });
}
```

The phrase "block_on" appears in this prose — that is fine, only
matches inside ```rust fences and inside async regions count.

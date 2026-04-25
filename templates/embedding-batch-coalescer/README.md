# embedding-batch-coalescer

A background-thread coalescer that turns a flood of single-item embedding requests into a small number of batched upstream calls — with a **size trigger**, a **wait-window trigger**, in-batch **dedup**, and **per-future error propagation** so a failed upstream call cannot silently swallow callers.

## The problem

Embedding APIs are billed and rate-limited per *call*, not per *vector*. A naive `embed(text)` wrapper that fires one HTTP request per call is the most expensive way to do retrieval: a single page-render that needs 40 query embeddings becomes 40 sequential round-trips, each paying full TLS + queueing + provider overhead. Even worse, in an async / multi-threaded service the calls fan out concurrently and you trip the provider's per-second request cap long before you trip its per-second token cap.

The fix everyone reaches for is "just batch them" — but the seam where that batching has to live is awkward. Callers want a synchronous-feeling `embed_one(text) -> vector`. The model wants `embed_many(texts) -> vectors`. The coalescer is the adapter between those two surfaces.

## The shape

```
caller --submit("hello")--> [coalescer queue] --flush--> embed_fn([...]) --> [vec, vec, ...]
                              |                                                 |
                              |  triggers:                                      |
                              |   * batch full                                  |
                              |   * window expired                              |
                              |   * close()                                     |
                              v                                                 v
                            Future <-------------- result fan-out ---------------+
```

`submit(text)` returns a `concurrent.futures.Future[list[float]]` immediately. A single background thread owns the pending queue and decides when to flush. The caller's `embed_fn` is a *batch* function (`Sequence[str] -> List[List[float]]`) — usually a thin wrapper over the provider's batch endpoint.

Three flush triggers, all checked under one lock:

1. **Batch full** (`len(pending) >= max_batch_size`). The latency-optimal trigger; flushes the moment a worker-sized batch is ready.
2. **Window expired** (`now - first_arrival >= max_wait_s`). The throughput / fairness floor; the *first* item in the batch is guaranteed to wait at most `max_wait_s` before going out, even on a slow trickle.
3. **Close** (`coalescer.close()`). Drains everything pending so shutdown does not orphan futures.

## In-batch dedup

Identical strings inside one flushed batch share one upstream slot, then fan out to every future at result time. For RAG over a small vocabulary of recurring queries, or for "embed every chunk" workloads where boilerplate headers repeat, the dedup ratio is often dramatic — the worked example shows 50 submits → 5 upstream items in scenario 3. Dedup is **per-batch**, not global; a real cache (`tool-result-cache`, `embedding-cache-eviction`) belongs *upstream of* the coalescer for cross-batch reuse.

## When to use it

- Any embedding-heavy path where `embed_one(text)` is called concurrently from multiple workers / requests.
- Indexing pipelines that walk a corpus and would otherwise issue one call per chunk.
- RAG query-time fan-out where an LLM-generated query plan produces several semantically-related searches at once.

## When NOT to use it

- Single-shot scripts that embed one document. The coalescer adds a thread and a lock for zero benefit.
- Workloads where every text is genuinely unique and arrives one-at-a-time, slower than `max_wait_s` apart — the coalescer degrades to "embed_one with extra steps." Set `max_wait_s=0` or skip the template.
- Workloads where ordering matters across batches in subtle ways. Within a single batch ordering is preserved; across batches the coalescer makes no promise.
- As a substitute for a cache. Dedup only helps within one flush window. For real cross-call savings, stack a cache in front.

## Knobs

| knob | default | notes |
|---|---|---|
| `max_batch_size` | 64 | Match your provider's batch limit; larger = fewer calls, but worse first-item latency. |
| `max_wait_s` | 0.05 | The latency floor a single late item is willing to add. 50ms is a good starting point for interactive paths; 200–500ms is fine for indexing. |
| `clock` | `time.monotonic` | Inject for tests. |

## Failure modes the implementation defends against

1. **Upstream raises.** Every future in the batch receives the same exception via `set_exception`; no future is left pending. Stats record `errors`.
2. **Upstream returns wrong-length result list.** Treated as an error and propagated to all futures with a clear message — better than silently zipping mismatched results.
3. **`submit` after `close`.** Returns a future that is already failed with `RuntimeError("coalescer is closed")`.
4. **Empty batch flush.** No-op.
5. **Concurrent submits during flush.** The flush takes a *snapshot* of the current pending list under the lock and releases the lock before calling `embed_fn`; new submits queue freely against the next batch.
6. **Daemon thread + `close()` join.** The worker is a daemon (so a crashed process doesn't hang on it) but `close(timeout=...)` waits for a clean drain.

## Files in this template

- `coalescer.py` — stdlib-only reference (~150 lines).
- `worked_example.py` — four scenarios: burst (size-flush), trickle (time-flush), dedup, and upstream-error propagation. Real threads, deterministic fake `embed_fn`, no network.

## Sample run

```text
== scenario 1: burst of 100 concurrent submits ==
  submitted=100 batches=4 by_size=3 by_time=1 by_close=0 upstream_items=100
  first result: [6.0, 61.0, 0.0]
  ok
== scenario 2: trickle (3 slow producers) ==
  submitted=3 batches=1 by_size=0 by_time=1 by_close=0
  ok
== scenario 3: heavy duplication ==
  submitted=50 upstream_items=5 (dedup ratio: 5/50)
  upstream_calls=1 batches=1
  ok
== scenario 4: upstream error propagates to every future in batch ==
  errors_propagated=5/5  msg='upstream down (would have embedded 5)'  stats.errors=1
  ok

All scenarios passed.
```

100 single-call submissions collapsed into 4 batches; 50 duplicated submissions collapsed into 1 upstream call of 5 items; an upstream failure surfaced cleanly to all 5 waiting futures with no orphaned pending state.

# Clean JSONL

A consistent schema across all rows:

```jsonl
{"id": 1, "name": "alice", "email": "a@x"}
{"id": 2, "name": "bob", "email": "b@x"}
{"id": 3, "name": "carol", "email": "c@x"}
```

Blank lines inside the block are tolerated:

```ndjson
{"event": "click", "ts": 1}

{"event": "scroll", "ts": 2}
{"event": "click", "ts": 3}
```

A non-JSONL fence next to it should be ignored entirely:

```text
Just prose here. {"id": 1} mentioned but not in a JSONL fence.
```

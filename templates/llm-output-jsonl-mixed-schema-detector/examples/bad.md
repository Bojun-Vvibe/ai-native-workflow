# Sample data the model produced

Twenty rows, please:

```jsonl
{"id": 1, "name": "alice", "email": "a@x"}
{"id": 2, "name": "bob"}
{"id": 3, "full_name": "carol", "email": "c@x"}
{"id": 4, "name": "dave", "email": "d@x", "age": 31}
```

A second block with a parse failure and a non-object record:

```ndjson
{"id": 1, "name": "alice"}
{"id": 2, "name": "bob",}
[1, 2, 3]
```

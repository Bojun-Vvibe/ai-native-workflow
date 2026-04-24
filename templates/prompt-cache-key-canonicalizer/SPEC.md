# SPEC: prompt cache key canonicalization

## Goal

Given any prompt-call descriptor:

```
{
  "model": str,
  "prompt": str | list,
  "temperature": float,
  "tools": list[obj]?,
  "context": any?
}
```

produce a stable SHA-256 hex digest such that two semantically identical
calls produce the same key, regardless of dict-key order, float
representation, or list ordering of *commutative* fields.

## Canonicalization rules

1. **Dict keys**: recursively sorted ascending by Unicode codepoint.
2. **Floats**:
   - `NaN` → key error (refuse — not cacheable).
   - `±inf` → key error.
   - Finite floats → formatted via `repr()` then re-parsed via `float()`
     and emitted with `format(x, '.17g')`. This produces the shortest
     round-trip-stable form.
3. **Strings**: emitted as JSON strings (UTF-8, escapes preserved).
4. **Lists**: order-preserving for `prompt` and `context`. For `tools`,
   sorted by each tool's `name` field (tool *order* is conventionally
   not semantic).
5. **Temperature**: rounded to 4 decimal places before canonicalization.
   `0.7000000001` and `0.7` are treated as equal.
6. **Missing optional fields**: omitted entirely (not emitted as `null`).
7. **Top-level wrapper**: always
   `{"context_hash": <sha256 of canonical context>, "model": ..., "prompt": ..., "temperature": ..., "tools": [...]}`
   so context is always summarized to a fixed-length hash before going
   into the outer key.

## Output

`canonicalize(desc) -> (canonical_json: str, key: str)` where `key` is
`sha256(canonical_json.encode("utf-8")).hexdigest()`.

## Non-goals

- Not a security primitive; collisions are cryptographically improbable
  but the goal is cache identity, not authentication.
- Not a schema validator. Garbage in, garbage-keyed garbage out — but
  deterministically.

# SPEC — structured-error-taxonomy

## Enums (stable; additions are backwards-compatible, removals are not)

### `class`
| value | meaning |
| --- | --- |
| `rate_limited` | provider asked us to slow down |
| `content_filter` | provider refused on policy grounds |
| `auth` | credentials missing/invalid/forbidden |
| `quota_exhausted` | billing/quota cap hit |
| `context_length` | request exceeded model's max context |
| `tool_timeout` | downstream tool took too long |
| `tool_unavailable` | downstream tool was 5xx |
| `tool_bad_input` | downstream tool rejected our request shape |
| `host_io` | local disk/process error |
| `transient_network` | likely-recoverable network blip |
| `unknown` | catch-all; refuse to retry |

### `retryability`
| value | meaning |
| --- | --- |
| `retry_now` | safe immediate retry (idempotent transient) |
| `retry_after` | retry after a delay |
| `retry_with_edit` | only retry if request is changed |
| `do_not_retry` | terminal under current request |

### `attribution`
| value | meaning |
| --- | --- |
| `vendor` | provider's fault |
| `caller` | our request was bad |
| `tool` | downstream tool |
| `host` | local infra |
| `unknown` | catch-all |

## Rule evaluation contract

1. Rules are evaluated **top-to-bottom, first match wins**.
2. Each rule is a pure function of the input record. Side effects are forbidden.
3. The catch-all (`default`) is guaranteed to match anything that no
   earlier rule matched, and emits `unknown / do_not_retry / unknown`.
4. The classifier never raises on a well-formed record (it may raise
   `ValueError` on missing/invalid required fields).
5. CLI exit codes:
    - `0` — every input matched a non-default rule
    - `1` — at least one input matched the catch-all
    - `2` — at least one input was malformed

## Required fields on input records

| field | type | notes |
| --- | --- | --- |
| `id` | string | opaque |
| `source` | enum | `model` \| `tool` \| `host` |

Optional but commonly present: `vendor_code`, `http_status`, `message`.

## Output record

| field | type | notes |
| --- | --- | --- |
| `id` | string | echoed from input |
| `class` | enum | from `CLASSES` |
| `retryability` | enum | from `RETRYABILITY` |
| `attribution` | enum | from `ATTRIBUTION` |
| `matched_rule` | string | rule id, or `default` |

## Composition contract

- The `class` value is the canonical `reason_class` consumed by
  `model-fallback-ladder`'s `skip_on_reason_classes`.
- The `retryability` value is the canonical `retry_class_hint` consumed
  by `tool-call-retry-envelope`.
- Only records with `attribution=tool` should count toward a tool's
  circuit-breaker failure rate.

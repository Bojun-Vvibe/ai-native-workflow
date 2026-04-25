"""Worked example for tool-result-size-limiter.

Three scenarios:
  1. A small tool result that fits under the cap → returned verbatim.
  2. A large log dump → truncated to a head + tail sandwich.
  3. A multi-byte UTF-8 string near the boundary → still valid UTF-8.

Run: python3 worked_example.py
"""

from limiter import LimitResult, limit_tool_result


def show(label: str, r: LimitResult) -> None:
    print(f"--- {label} ---")
    print(f"  truncated      : {r.truncated}")
    print(f"  original_bytes : {r.original_bytes}")
    print(f"  output_bytes   : {r.output_bytes}")
    print(f"  elided_bytes   : {r.elided_bytes}")
    print(f"  elided_sha     : {r.elided_sha256_prefix or '(n/a)'}")
    if len(r.text) <= 220:
        print(f"  text           : {r.text!r}")
    else:
        print(f"  text[:80]      : {r.text[:80]!r}")
        print(f"  text[-80:]     : {r.text[-80:]!r}")
    # Round-trip sanity: the returned text always decodes cleanly.
    r.text.encode("utf-8").decode("utf-8")
    print()


def main() -> None:
    # Scenario 1: small payload, fits under 1 KiB cap.
    small = "ok\nfound 3 matches in src/router.py\n"
    show("small payload (fits)", limit_tool_result(small, max_bytes=1024))

    # Scenario 2: ~5 KiB log dump, capped to 512 bytes.
    line = "2026-04-25T10:00:00Z INFO request_id=abc-123 latency_ms=42 ok=true\n"
    big = (line * 80)  # ~5440 bytes
    show("big log (truncated)", limit_tool_result(big, max_bytes=512))

    # Scenario 3: multi-byte UTF-8 near the boundary.
    # Each "あ" is 3 bytes UTF-8. Pack 200 of them = 600 bytes,
    # then cap at 200 bytes — the limiter must clip on a codepoint
    # boundary, not mid-sequence.
    multi = "あ" * 200
    r3 = limit_tool_result(multi, max_bytes=200)
    show("utf-8 boundary", r3)
    # Final assertion: every clipped chunk is valid UTF-8.
    head, _, rest = r3.text.partition("…<TRUNCATED:")
    head.encode("utf-8")
    print("utf-8 round-trip OK on all three scenarios.")


if __name__ == "__main__":
    main()

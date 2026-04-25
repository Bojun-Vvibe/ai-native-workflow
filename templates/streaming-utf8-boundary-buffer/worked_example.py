"""worked_example.py — six scenarios for Utf8BoundaryBuffer.

Run with:
    python3 worked_example.py
"""

from __future__ import annotations

from utf8_boundary_buffer import Utf8BoundaryBuffer, Utf8BoundaryError


def _hex(b: bytes) -> str:
    return " ".join(f"{x:02x}" for x in b)


def scenario_clean_ascii() -> None:
    print("== clean_ascii ==")
    buf = Utf8BoundaryBuffer()
    out = []
    for chunk in [b"hello", b" ", b"world"]:
        out.append(buf.feed(chunk))
    out.append(buf.flush())
    print(f"  emitted: {''.join(out)!r}")
    print(f"  pending_bytes after flush: {buf.pending_bytes}")
    assert "".join(out) == "hello world"
    assert buf.pending_bytes == 0


def scenario_split_3byte_codepoint() -> None:
    # 中 = U+4E2D = e4 b8 ad
    print("== split_3byte_codepoint ==")
    buf = Utf8BoundaryBuffer()
    a = buf.feed(b"hi \xe4\xb8")           # split mid-codepoint
    print(f"  feed(b'hi \\xe4\\xb8') -> {a!r}  pending={buf.pending_bytes}")
    b = buf.feed(b"\xad ok")                # completes 中
    print(f"  feed(b'\\xad ok')        -> {b!r}  pending={buf.pending_bytes}")
    c = buf.flush()
    full = a + b + c
    print(f"  full: {full!r}")
    assert a == "hi "
    assert b == "中 ok"
    assert full == "hi 中 ok"


def scenario_split_4byte_emoji() -> None:
    # 🐱 = U+1F431 = f0 9f 90 b1, split as 1+3 then 2+2 then 3+1
    print("== split_4byte_emoji ==")
    raw = "cat 🐱 sees 🐱!".encode("utf-8")
    print(f"  raw bytes: {_hex(raw)}")
    # Split deliberately at every offset that lands inside an emoji.
    for split_at in (5, 6, 7, 13, 14, 15):
        buf = Utf8BoundaryBuffer()
        a = buf.feed(raw[:split_at])
        b = buf.feed(raw[split_at:])
        c = buf.flush()
        full = a + b + c
        ok = full == "cat 🐱 sees 🐱!"
        print(f"  split@{split_at:>2}  pending_after_first_feed=?  full_ok={ok}")
        assert ok


def scenario_continuation_only_chunk() -> None:
    # First chunk ends with a 2-byte leader; second chunk is *only* the
    # continuation byte. The buffer must hold the leader, then drain on the
    # second feed.
    print("== continuation_only_chunk ==")
    buf = Utf8BoundaryBuffer()
    # ñ = U+00F1 = c3 b1
    a = buf.feed(b"hola \xc3")
    b = buf.feed(b"\xb1")
    c = buf.flush()
    print(f"  a={a!r}  b={b!r}  c={c!r}  total={(a+b+c)!r}")
    assert a == "hola "
    assert b == "ñ"
    assert c == ""


def scenario_torn_at_eof() -> None:
    # Stream ends mid-codepoint -> flush() raises.
    print("== torn_at_eof ==")
    buf = Utf8BoundaryBuffer()
    a = buf.feed(b"oops \xe4\xb8")  # leader + 1 continuation, missing 1
    print(f"  a={a!r}  pending_bytes={buf.pending_bytes}")
    raised = False
    try:
        buf.flush()
    except Utf8BoundaryError as e:
        raised = True
        print(f"  flush() raised: {e}")
    assert raised
    assert buf.pending_bytes == 0  # flush clears the buffer even on raise


def scenario_invalid_byte_in_complete_prefix() -> None:
    # An invalid byte inside the *complete* prefix surfaces immediately on
    # feed(), not deferred to flush().
    print("== invalid_byte_in_complete_prefix ==")
    buf = Utf8BoundaryBuffer()
    raised = False
    try:
        buf.feed(b"good \xff bad")
    except UnicodeDecodeError as e:
        raised = True
        print(f"  feed() raised: {e.reason}")
    assert raised


def main() -> None:
    scenario_clean_ascii()
    scenario_split_3byte_codepoint()
    scenario_split_4byte_emoji()
    scenario_continuation_only_chunk()
    scenario_torn_at_eof()
    scenario_invalid_byte_in_complete_prefix()
    print("\nAll assertions passed.")


if __name__ == "__main__":
    main()

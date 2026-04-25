"""Worked example for streaming-line-delimiter-buffer.

Five parts, all run end-to-end with stdlib only:

  1. Single-byte feeding — a 4-line NDJSON document arrives one byte at
     a time and is reassembled into exactly 4 lines.
  2. CRLF delimiter split across chunks — b"...\\r" + b"\\n..." must
     join correctly.
  3. Trailing partial line at close — non-strict mode yields it,
     strict mode raises.
  4. LineTooLong defends against an unbounded "line" that never sees
     a delimiter.
  5. feed-after-close and close-after-close raise BufferClosed.
"""

from __future__ import annotations

import json

from line_buffer import (
    BufferClosed,
    LineBuffer,
    LineTooLong,
    UnterminatedTrailingLine,
)


def section(title: str) -> None:
    print(f"\n--- {title} ---")


def part_1_byte_drip() -> None:
    section("Part 1: NDJSON dripped one byte at a time")
    payload = (
        b'{"step":0,"event":"start"}\n'
        b'{"step":1,"event":"tool_call","tool":"read_file"}\n'
        b'{"step":2,"event":"tool_result","ok":true}\n'
        b'{"step":3,"event":"done"}\n'
    )
    buf = LineBuffer(delimiter=b"\n", max_line_bytes=4096)
    lines: list[bytes] = []
    for byte in payload:
        lines.extend(buf.feed(bytes([byte])))
    lines.extend(buf.close())
    print(f"emitted {len(lines)} lines (expected 4)")
    for line in lines:
        rec = json.loads(line)
        print(f"  step={rec['step']:>2} event={rec['event']}")
    assert len(lines) == 4
    assert json.loads(lines[2])["ok"] is True


def part_2_crlf_split_across_chunks() -> None:
    section("Part 2: CRLF delimiter split across chunk boundary")
    buf = LineBuffer(delimiter=b"\r\n")
    out = []
    out.extend(buf.feed(b"event: token\r"))   # ends mid-CRLF
    out.extend(buf.feed(b"\ndata: hello\r\n"))  # completes prior line + new line
    out.extend(buf.close())
    print(f"out = {out!r}")
    assert out == [b"event: token", b"data: hello"], out


def part_3_trailing_partial_line() -> None:
    section("Part 3: trailing line at close (lenient vs strict)")
    # Lenient: trailing un-terminated line is yielded.
    buf = LineBuffer(strict_trailing=False)
    out = buf.feed(b"line-a\nline-b-no-newline")
    out.extend(buf.close())
    print(f"lenient: {out!r}")
    assert out == [b"line-a", b"line-b-no-newline"]

    # Strict: trailing un-terminated line raises.
    buf2 = LineBuffer(strict_trailing=True)
    buf2.feed(b"line-a\nline-b-no-newline")
    try:
        buf2.close()
    except UnterminatedTrailingLine as exc:
        print(f"strict raised as expected: {exc} (length={exc.length})")
        assert exc.length == len(b"line-b-no-newline")
    else:
        raise AssertionError("strict mode did not raise")


def part_4_line_too_long_defends_memory() -> None:
    section("Part 4: LineTooLong defends against delimiter-starved streams")
    buf = LineBuffer(max_line_bytes=64)
    # Feed 200 bytes with no delimiter. Must raise long before we
    # buffer the whole thing — and certainly before close().
    payload = b"A" * 200
    try:
        buf.feed(payload)
    except LineTooLong as exc:
        print(
            f"raised LineTooLong(observed={exc.observed_bytes}, "
            f"limit={exc.limit}) — buffer cleared"
        )
        assert exc.limit == 64
        assert exc.observed_bytes == 200
        # After raising, the buffer was cleared; further feeds work.
        out = buf.feed(b"short\n")
        assert out == [b"short"], out
        print(f"recovery feed after raise: {out!r}")
    else:
        raise AssertionError("LineTooLong was not raised")


def part_5_closed_buffer_rejects_input() -> None:
    section("Part 5: post-close calls raise BufferClosed")
    buf = LineBuffer()
    buf.feed(b"hi\n")
    buf.close()
    for action_name, action in (
        ("feed", lambda: buf.feed(b"more\n")),
        ("close", lambda: buf.close()),
    ):
        try:
            action()
        except BufferClosed as exc:
            print(f"{action_name}() after close raised: {exc}")
        else:
            raise AssertionError(f"{action_name}() did not raise after close")


def main() -> None:
    part_1_byte_drip()
    part_2_crlf_split_across_chunks()
    part_3_trailing_partial_line()
    part_4_line_too_long_defends_memory()
    part_5_closed_buffer_rejects_input()
    print("\nAll 5 parts OK.")


if __name__ == "__main__":
    main()

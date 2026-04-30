"""Bad: assert as bounds check in parser."""

def parse_record(buf, offset):
    assert offset + 4 <= len(buf), "truncated record"
    length = int.from_bytes(buf[offset:offset + 4], "big")
    return length

"""Worked example: seven cases exercising the BOM-byte detector."""

from detector import detect_boms, format_report, has_blocking_bom


def run(label: str, data: bytes, *, fail_on_leading: bool = False) -> None:
    print(f"=== {label} ===")
    findings = detect_boms(data)
    print(format_report(findings))
    blocking = has_blocking_bom(findings, fail_on_leading=fail_on_leading)
    print(f"blocking(fail_on_leading={fail_on_leading}): {blocking}")
    print()


def main() -> None:
    # 01 clean ASCII payload, no BOMs anywhere
    run("01 clean ascii", b"#!/bin/sh\necho hello\n")

    # 02 leading UTF-8 BOM only — tolerable for prose, fatal for shell/JSON
    run("02 leading utf-8 bom only", b"\xef\xbb\xbf{\n  \"ok\": true\n}\n",
        fail_on_leading=True)

    # 03 leading UTF-16-LE BOM
    run("03 leading utf-16-le bom",
        b"\xff\xfeh\x00e\x00l\x00l\x00o\x00")

    # 04 mid-stream UTF-8 BOM (concatenation accident: file_a + file_b)
    run("04 mid-stream utf-8 bom (concat accident)",
        b"part one\n" + b"\xef\xbb\xbf" + b"part two\n")

    # 05 leading UTF-32-LE BOM — must NOT mis-classify as UTF-16-LE
    # (UTF-16-LE BOM is a prefix of UTF-32-LE BOM)
    run("05 leading utf-32-le bom (utf-16-le prefix trap)",
        b"\xff\xfe\x00\x00h\x00\x00\x00")

    # 06 leading UTF-16-LE plus a mid-stream UTF-8 BOM
    run("06 utf-16-le leading + utf-8 mid-stream",
        b"\xff\xfedata-a\xef\xbb\xbfdata-b")

    # 07 GB18030 leading BOM (rare but real CN tooling)
    run("07 gb18030 leading bom",
        b"\x84\x31\x95\x33hello-from-gb18030")


if __name__ == "__main__":
    main()

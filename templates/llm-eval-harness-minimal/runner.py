#!/usr/bin/env python3
"""
Minimal LLM eval harness — runner.

Usage:
    python3 runner.py manifest.yaml [--report report.md]

Loads a YAML manifest of test cases, runs each against an agent_under_test
function, grades the output, and writes a markdown report.

Replace agent_under_test() with a call to your real agent.
"""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.stderr.write("PyYAML required: pip install pyyaml\n")
    sys.exit(2)


# --- Agent under test --------------------------------------------------------

def agent_under_test(input_text: str) -> str:
    """
    Replace this with a call into your real agent (subprocess, HTTP, library).
    The stub returns a placeholder string so the harness can be smoke-tested
    end-to-end without a real model attached.
    """
    return "STUB OUTPUT — replace agent_under_test() with a real call."


# --- Graders -----------------------------------------------------------------

def grade_exact(output: str, expected) -> tuple[bool, str]:
    target = expected if isinstance(expected, str) else expected.get("value", "")
    return (output.strip() == target.strip(), f"expected exact match: {target!r}")


def grade_contains_all(output: str, expected) -> tuple[bool, str]:
    needles = expected if isinstance(expected, list) else expected.get("contains_all", [])
    missing = [n for n in needles if n.lower() not in output.lower()]
    if missing:
        return (False, f"missing substrings: {missing}")
    return (True, f"all {len(needles)} substrings present")


def grade_contains_any(output: str, expected) -> tuple[bool, str]:
    needles = expected if isinstance(expected, list) else expected.get("contains_any", [])
    hits = [n for n in needles if n.lower() in output.lower()]
    if hits:
        return (True, f"matched: {hits}")
    return (False, f"none of {needles} present")


def grade_regex(output: str, expected) -> tuple[bool, str]:
    pattern = expected if isinstance(expected, str) else expected.get("regex", "")
    if re.search(pattern, output):
        return (True, f"regex matched: {pattern!r}")
    return (False, f"regex did NOT match: {pattern!r}")


def grade_json_schema(output: str, expected) -> tuple[bool, str]:
    """Tiny subset of JSON Schema: required keys, top-level enum/type/array hints."""
    schema = expected.get("json_schema", expected) if isinstance(expected, dict) else {}
    try:
        data = json.loads(output)
    except (json.JSONDecodeError, TypeError) as e:
        return (False, f"output is not valid JSON: {e}")
    required = schema.get("required", [])
    missing = [k for k in required if k not in data]
    if missing:
        return (False, f"missing required keys: {missing}")
    props = schema.get("properties", {})
    for key, rule in props.items():
        if key not in data:
            continue
        if "enum" in rule and data[key] not in rule["enum"]:
            return (False, f"key {key!r} not in enum {rule['enum']}: got {data[key]!r}")
        if rule.get("type") == "array" and not isinstance(data[key], list):
            return (False, f"key {key!r} expected array, got {type(data[key]).__name__}")
        if rule.get("type") == "string" and not isinstance(data[key], str):
            return (False, f"key {key!r} expected string, got {type(data[key]).__name__}")
    return (True, f"schema satisfied (required={required})")


def grade_llm_judge(output: str, expected) -> tuple[bool, str]:
    """Stub. Wire to your provider if you want LLM-as-judge. Use sparingly."""
    return (False, "llm_judge grader not configured — wire to your provider")


GRADERS = {
    "exact": grade_exact,
    "contains_all": grade_contains_all,
    "contains_any": grade_contains_any,
    "regex": grade_regex,
    "json_schema": grade_json_schema,
    "llm_judge": grade_llm_judge,
}


# --- Runner ------------------------------------------------------------------

def run(manifest_path: Path) -> list[dict]:
    with manifest_path.open() as f:
        manifest = yaml.safe_load(f)
    results = []
    for case in manifest.get("cases", []):
        case_id = case["id"]
        grader_name = case.get("grader", "exact")
        grader = GRADERS.get(grader_name)
        if grader is None:
            results.append({
                "id": case_id, "passed": False,
                "detail": f"unknown grader: {grader_name}",
                "output": "", "grader": grader_name,
            })
            continue
        try:
            output = agent_under_test(case["input"])
        except Exception as e:
            results.append({
                "id": case_id, "passed": False,
                "detail": f"agent error: {e}",
                "output": "", "grader": grader_name,
            })
            continue
        passed, detail = grader(output, case["expected"])
        results.append({
            "id": case_id, "passed": passed,
            "detail": detail, "output": output, "grader": grader_name,
            "description": case.get("description", ""),
        })
    return results


def render_report(results: list[dict], manifest_path: Path) -> str:
    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    lines = [
        f"# Eval report: {manifest_path.name}",
        "",
        f"Run at: {datetime.now(timezone.utc).isoformat()}",
        f"Result: **{passed}/{total} passed** ({100*passed/total:.0f}%)" if total else "No cases.",
        "",
        "## Per-case results",
        "",
        "| Case | Grader | Verdict | Detail |",
        "|---|---|---|---|",
    ]
    for r in results:
        verdict = "PASS" if r["passed"] else "FAIL"
        lines.append(f"| `{r['id']}` | {r['grader']} | **{verdict}** | {r['detail']} |")
    lines.extend(["", "## Failures (full output)", ""])
    for r in results:
        if r["passed"]:
            continue
        lines.extend([
            f"### `{r['id']}`",
            f"- Description: {r.get('description','(none)')}",
            f"- Detail: {r['detail']}",
            "- Output:",
            "```",
            r["output"][:2000],
            "```",
            "",
        ])
    return "\n".join(lines)


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("manifest", type=Path)
    p.add_argument("--report", type=Path, default=Path("report.md"))
    args = p.parse_args(argv)
    results = run(args.manifest)
    report = render_report(results, args.manifest)
    args.report.write_text(report)
    failures = sum(1 for r in results if not r["passed"])
    print(f"wrote {args.report}: {len(results)-failures}/{len(results)} passed")
    sys.exit(0 if failures == 0 else 1)


if __name__ == "__main__":
    main()

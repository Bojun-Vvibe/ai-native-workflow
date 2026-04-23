#!/usr/bin/env bash
# Run the validator against three fixtures, print results.
set -u
cd "$(dirname "$0")/.."
PYTHONPATH=src python3 - <<'PY'
import json, pathlib
from validate import validate, ValidationError, RepairRequest

schema = json.loads(pathlib.Path("schemas/finding.schema.json").read_text())
fixtures = ["good.json", "malformed.json", "drifted.json"]

for name in fixtures:
    raw = pathlib.Path(f"examples/fixtures/{name}").read_text()
    print(f"--- fixture: {name}")
    # Try strict reject first.
    try:
        result = validate(raw, schema, policy="reject")
        print(f"  reject:        PASS  ({len(json.dumps(result))} bytes)")
    except ValidationError as e:
        print(f"  reject:        FAIL  {e}")
    # Then repair_once.
    res = validate(raw, schema, policy="repair_once")
    if isinstance(res, RepairRequest):
        print(f"  repair_once:   needs repair  ({res.error[:60]}...)")
    else:
        print(f"  repair_once:   PASS")
PY

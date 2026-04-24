"""Worked example: route a JSON-extraction prompt to three fake models,
score by (parses + has required keys + value plausibility), pick winner.

Uses simulated model responses so the example is fully reproducible
without any provider keys. Replace `fake_call` with a real client.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from arbiter import arbitrate  # noqa: E402


PROMPT = (
    "Extract the city, country, and temperature_c from this sentence "
    "as JSON with exactly those three keys: "
    "'It was 14 degrees Celsius in Lisbon, Portugal yesterday.'"
)

# Three fake models with different failure modes:
#   model-a: returns valid JSON, correct values
#   model-b: returns JSON wrapped in markdown fence (parses after strip)
#   model-c: returns prose, no JSON at all
FAKE_RESPONSES = {
    "model-a": '{"city": "Lisbon", "country": "Portugal", "temperature_c": 14}',
    "model-b": (
        "```json\n"
        '{"city": "Lisbon", "country": "Portugal", "temperature_c": 14}\n'
        "```"
    ),
    "model-c": "The city was Lisbon and it was about fourteen degrees.",
}


def fake_call(model: str, prompt: str) -> str:
    return FAKE_RESPONSES[model]


REQUIRED_KEYS = {"city", "country", "temperature_c"}


def strip_fence(s: str) -> str:
    s = s.strip()
    if s.startswith("```"):
        # drop first line, drop trailing fence
        lines = s.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        s = "\n".join(lines)
    return s.strip()


def criterion(prompt: str, response: str) -> tuple[float, dict]:
    evidence: dict = {}
    cleaned = strip_fence(response)
    evidence["had_fence"] = cleaned != response.strip()
    try:
        obj = json.loads(cleaned)
    except json.JSONDecodeError as e:
        evidence["parse_error"] = str(e)
        return -1.0, evidence

    if not isinstance(obj, dict):
        evidence["type_error"] = type(obj).__name__
        return -0.5, evidence

    keys = set(obj.keys())
    evidence["keys"] = sorted(keys)
    missing = REQUIRED_KEYS - keys
    extra = keys - REQUIRED_KEYS
    score = 1.0
    if missing:
        evidence["missing"] = sorted(missing)
        score -= 0.5 * len(missing)
    if extra:
        evidence["extra"] = sorted(extra)
        score -= 0.1 * len(extra)
    # Penalize markdown-fence noise slightly: clean wins on ties.
    if evidence["had_fence"]:
        score -= 0.05
    # Plausibility: temperature numeric in -50..60
    t = obj.get("temperature_c")
    if isinstance(t, (int, float)) and -50 <= t <= 60:
        evidence["temperature_plausible"] = True
    else:
        evidence["temperature_plausible"] = False
        score -= 0.3
    return score, evidence


def main() -> None:
    result = arbitrate(
        PROMPT,
        models=["model-a", "model-b", "model-c"],
        model_call=fake_call,
        criterion=criterion,
        label="json-extraction-demo",
    )
    print(result.to_json())
    print()
    print(f"WINNER: {result.winner}  score={result.winner_score:.3f}")


if __name__ == "__main__":
    main()

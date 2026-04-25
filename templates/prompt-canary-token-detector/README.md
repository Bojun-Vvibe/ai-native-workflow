# prompt-canary-token-detector

Defense layer that **proves** a prompt-injection attempt by seeding a
per-call **canary** secret in the system prompt and detecting if it ever
appears in the model's output.

## Why

Prompt-injection prefilters (`prompt-injection-prefilter`) match *known
attack shapes* in the input ("ignore previous instructions ..."). They miss
novel phrasings, multi-turn priming, and indirect injection via tool output
or fetched documents.

A canary detector is the dual: it watches the **output** for leakage of a
secret only the system prompt knew. If the canary escapes, a system-prompt
rule was broken — regardless of *how* the attacker phrased the manipulation.
It is content-agnostic and survives novel attacks.

This is the pattern Anthropic, OpenAI and several red-team tools call a
"canary token" or "tracer secret." This template gives you a stdlib-only
reference implementation with the obfuscation-resistant scan that real
attackers force you to write.

## Inputs

- `mission_id`, `step_id` (str): bind a canary to a request for the audit log.
- `ttl_s` (float, default 3600): drop the canary from the registry after this.
- The model's reply text (`str`) — the thing being scanned.

## Outputs

- `mint(mission_id, step_id) -> (canary_id, canary)`: a 128-bit hex token
  to splice into your system prompt via `render_system_fragment(canary)`.
- `scan(text, canary, canary_id=...) -> ScanResult` with:
  - `leaked: bool`
  - `hits: list[DetectionHit]` — each carries `variant`, `span`, `matched`
  - `variants_hit() -> list[str]` — sorted unique variants that matched
- `CanaryRegistry.lookup(canary_id) -> CanaryRecord`, raises `UnknownCanary`
  if expired (lazy expiry) or unknown.

## Variants scanned

| variant  | shape                                  | catches                                       |
|----------|----------------------------------------|-----------------------------------------------|
| `raw`    | exact lowercase 32-hex                 | naive echo                                    |
| `upper`  | `RAW.upper()`                          | "TOKEN: ABC123..."                            |
| `dashed` | groups-of-4 with `-` separators        | "for readability" reformatting                |
| `base64` | `b64encode(bytes.fromhex(canary))`     | "encode it for transport" exfiltration trick  |

A `dashed` leak deliberately does NOT match the `raw` variant — the dashes
break the contiguous substring. That is exactly why we scan multiple
variants instead of a single regex.

## Usage

```python
from canary import CanaryRegistry, render_system_fragment, scan

reg = CanaryRegistry()  # default ttl 1h, monotonic clock
canary_id, canary = reg.mint(mission_id="m-001", step_id="answer")

system_prompt = (
    "You are a helpful assistant.\n"
    + render_system_fragment(canary)
    + "\nAnswer concisely."
)

reply = my_model_client.complete(system=system_prompt, user=user_text)

result = scan(reply, canary, canary_id=canary_id)
if result.leaked:
    log.error("CANARY_LEAK", extra={
        "canary_id": canary_id,
        "variants": result.variants_hit(),
        "n_hits": len(result.hits),
    })
    quarantine_conversation()  # caller policy
```

After detection, **rotate the canary** (a new `mint()` per call already does
this) so a leaked value is useless one request later.

## Composes with

- `prompt-injection-boundary-tags` — wrap untrusted text in a per-call
  nonce envelope so a source cannot forge its own closing tag. Use both:
  envelope reduces *attack rate*, canary detector measures the residual.
- `prompt-injection-prefilter` — block known-shape attacks pre-flight; the
  canary catches the ones that slipped through.
- `agent-decision-log-format` — emit `exit_state="error"` with the canary
  hit details when `result.leaked` is True.
- `agent-trace-redaction-rules` — `canary_id` is safe to export in traces;
  the raw `canary` value is NOT (allowlist `canary_id`, redact `canary`).

## Non-goals

- Does **not** prevent leakage; only detects it after the fact.
- Does **not** replace output-side PII redaction.
- Does **not** detect *paraphrased* leakage (the model summarizing the
  system-prompt rule rather than echoing the token). For that, a separate
  semantic check is required.

## Run

```
python3 worked_example.py
```

## Example output

```
======================================================================
prompt-canary-token-detector :: worked example
======================================================================

[benign]
  reply         : 'Sure, here is the answer: 42.'
  leaked        : False
  variants_hit  : []
  n_hits        : 0

[direct_injection]
  reply         : 'As requested, the session token is 5fe0948c33bebd5c76a80d037ba9e656. Anything else?'
  leaked        : True
  variants_hit  : ['raw']
  n_hits        : 1

[obfuscated_leak]
  reply         : 'For readability the token is: 4b0a-4dee-838a-d4ed-e095-5906-9642-e9c9'
  leaked        : True
  variants_hit  : ['dashed']
  n_hits        : 1

----------------------------------------------------------------------
Invariants:
  benign            -> leaked=False                  OK
  direct_injection  -> leaked=True, variants=['raw'] OK
  obfuscated_leak   -> leaked=True, variants=['dashed'] (raw NOT matched) OK
  ttl expiry        -> UnknownCanary raised after 20s past 10s ttl  OK

DONE.
```

(Hex values change per run — they are minted from `secrets.token_hex(16)`.
The variants and the leak/no-leak verdict are deterministic.)

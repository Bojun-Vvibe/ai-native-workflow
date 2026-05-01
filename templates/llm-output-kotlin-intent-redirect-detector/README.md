# llm-output-kotlin-intent-redirect-detector

Pure-stdlib python3 line scanner that flags Android intent-redirection
patterns in LLM-emitted Kotlin: a component receives an `Intent` from
an external caller, pulls a nested `Intent` / component name / extras
bundle out of it, and immediately launches that data without
validating the destination.

A finding is reported only when the same file contains both an
extraction from incoming extras **and** a launch (`startActivity`,
`startService`, `sendBroadcast`, `PendingIntent.getActivity`, …) **and**
the file never opts in to any of the recognised mitigations.

## Why

Android's `Intent` system is the canonical confused-deputy surface on
the platform. A component exported to other apps (or any
`PendingIntent` it produces) inherits the privileged identity of the
host. If the host extracts a target from caller-controlled extras and
then launches it as itself, the caller can pivot into Activities the
host alone is permitted to start — including `exported=false`
internals, permission-guarded screens, and chained `setResult` /
`onActivityResult` flows.

Google Play's App Security Improvement Program tracks this class as
"Intent Redirection" and ships explicit guidance: resolve the target
through the `PackageManager`, gate it behind an allowlist, set the
target component / package explicitly to a known class, or — for
`PendingIntent` — mark them `FLAG_IMMUTABLE` (mandatory on Android 12+
when targeting `S`).

CWE references:

- **CWE-927**: Use of Implicit Intent for Sensitive Communication.
- **CWE-441**: Unintended Proxy or Intermediary ('Confused Deputy').
- **CWE-829**: Inclusion of Functionality from Untrusted Control Sphere.

## Usage

```sh
python3 detect.py path/to/Foo.kt
python3 detect.py path/to/src/   # recurses *.kt
```

Exit code 1 if any unsafe usage found, 0 otherwise.

## What it flags

A `.kt` file that contains BOTH:

1. A read from incoming intent extras —
   `intent.getParcelableExtra(...)`, `getStringExtra(...)`,
   `getBundleExtra(...)`, `getSerializableExtra(...)`, etc.
2. A launch surface —
   `startActivity(...)` / `startActivityForResult(...)` /
   `startService(...)` / `startForegroundService(...)` /
   `bindService(...)` / `sendBroadcast(...)` /
   `sendOrderedBroadcast(...)` / `PendingIntent.getActivity(...)` /
   `PendingIntent.getBroadcast(...)` / `PendingIntent.getService(...)`.

…**only when** the same file contains none of the recognised
mitigations.

## What it does NOT flag

- Files that opt in to any mitigation, including:
  - `resolveActivity(...)` / `resolveActivityInfo(...)` /
    `queryIntentActivities(...)` (target validation through
    `PackageManager`).
  - `PendingIntent.FLAG_IMMUTABLE` (caller cannot rewrite the wrapped
    intent).
  - `setPackage("...")` / `setClassName("...", "...")` /
    `ComponentName("...", "...")` with both arguments as string
    literals (target is hard-coded, not caller-controlled).
  - Project-defined sentinels `INTENT_REDIRECT_ALLOWLIST` or
    `validateRedirectTarget`.
- Lines suffixed with `// intent-ok`.
- Extraction or launch occurring only inside string literals (regular
  `"..."` or triple `"""..."""`) or after `//` line comments — handled
  by a Kotlin-aware line stripper.
- Files that only extract OR only launch — both must be present, on
  the basis that pure data extraction without re-launch is not a
  redirect.

This is intentionally coarse. Pair with a stricter SAST tool if you
need per-call-site proof.

## Worked example

```sh
cd templates/llm-output-kotlin-intent-redirect-detector
./verify.sh
```

`verify.sh` runs the detector against `examples/bad/` (multiple
positive cases — Activity redirect via `getParcelableExtra`,
component-name redirect via `getStringExtra`, broadcast redirect, and
mutable `PendingIntent.getActivity`) and `examples/good/` (the same
shapes paired with `resolveActivity`, an explicit hard-coded
`setClassName`, `FLAG_IMMUTABLE`, plus suppressed and string-literal
false-positive cases). It asserts:

- detector exits non-zero on `bad/` with at least the expected number
  of findings,
- detector exits zero on `good/` with zero findings,
- prints `PASS` if both hold.

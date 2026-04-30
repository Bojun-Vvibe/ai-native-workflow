# llm-output-swift-ats-allows-arbitrary-loads-detector

Static detector for iOS / macOS `Info.plist` files emitted by an LLM that
disables App Transport Security (ATS) — i.e. opens the app to **CWE-319
cleartext transmission of sensitive information** by allowing plaintext
HTTP, weak TLS, or unrestricted exception domains.

## Why this matters for LLM output

When an LLM is asked "my fetch is failing in the simulator, fix it", a very
common — and very wrong — fix is:

```xml
<key>NSAppTransportSecurity</key>
<dict>
    <key>NSAllowsArbitraryLoads</key>
    <true/>
</dict>
```

That single key globally disables ATS for the entire app. The "fix" silences
the symptom (a `NSURLErrorDomain -1022` on an `http://` URL) by opening the
app to MITM on every connection. The right answer is almost always: switch
the upstream to HTTPS, or — if a single legacy host is genuinely required —
add a tightly scoped `NSExceptionDomains` entry, never a global allow.

## Sinks flagged

| ID                                 | Plist pattern                                              |
| ---------------------------------- | ---------------------------------------------------------- |
| `ats-allows-arbitrary-loads`       | `NSAllowsArbitraryLoads` set to `<true/>`                  |
| `ats-allows-arbitrary-loads-media` | `NSAllowsArbitraryLoadsForMedia` = `true`                  |
| `ats-allows-arbitrary-loads-web`   | `NSAllowsArbitraryLoadsInWebContent` = `true`              |
| `ats-allows-local-networking`      | `NSAllowsLocalNetworking` = `true` (less severe but flagged) |
| `ats-exception-allows-insecure`    | `NSExceptionAllowsInsecureHTTPLoads` = `true` in any domain |
| `ats-exception-min-tls-low`        | `NSExceptionMinimumTLSVersion` = `TLSv1.0` or `TLSv1.1`    |

## Usage

```sh
python3 detect.py path/to/sources
```

Walks the path looking for `Info.plist` (XML form) and any `*.plist` file.
Exit `1` if any flag triggers, `0` otherwise.

## Run the worked example

```sh
./verify.sh
```

`examples/bad/` contains 6 plists, each tripping a distinct rule;
`examples/good/` contains 3 plists that either omit the keys, set them to
`false`, or use a tightly-scoped `NSExceptionDomains` entry.

## Pitfalls / known limitations

- **XML plist only.** Binary `.plist` files (`bplist00`) are skipped — Apple
  ships those after `plutil -convert binary1`. Convert to xml1 first if you
  need to scan a built bundle: `plutil -convert xml1 Info.plist -o -`.
- The detector is **key-presence based**. A plist that sets
  `NSAllowsArbitraryLoads` = `<false/>` together with a permissive
  `NSExceptionDomains` would only fire on the exception entry, which is the
  intended behaviour but worth knowing.
- It does **not** read the actual URLs your app talks to — a perfectly
  scoped ATS config that exempts an attacker-controlled host is still wrong,
  but is invisible to a static plist scan.
- Property-list comments (`<!-- ... -->`) wrapping a key do **not** suppress
  the finding; remove or rename the key to silence.

# llm-output-typescript-any-overuse-detector

## What it detects

Counts `: any` type annotations and `as any` casts inside TypeScript code
fences (```ts / ```tsx / ```typescript) of an LLM-produced markdown
document. Each occurrence is reported with the fence index, the line
number within the fence, and the matched snippet.

Detected forms:

- Parameter or variable annotation: `foo: any`, `bar: any[]`, `baz: any | null`
- Return type: `function f(): any`, `(): any =>`
- Cast: `value as any`
- Generic with any: `Array<any>`, `Record<string, any>`, `Promise<any>`

## Why it matters

LLMs that don't fully understand a TypeScript domain reach for `any` to
silence the type checker. A code review surface with one or two `any`s
might be intentional; ten in a 60-line snippet usually means the
generated code wasn't actually type-checked. Flagging this lets a human
reviewer (or a downstream agent) re-prompt for stricter types or run
`tsc --noImplicitAny` before merging.

## How to use

```
python3 detector.py path/to/llm-output.md
```

Exit code is `0` whether or not findings were emitted; the script is
informational. Findings are printed one per line as:

```
fence#<idx> line<N>: <reason> -> <snippet>
```

The last line is always `total findings: <N>`. To gate a CI job, count
non-zero findings or grep the totals line.

The detector is markdown-fence-aware: text outside ```ts / ```tsx /
```typescript fences is ignored, so prose like "use any of the
following" does not trigger.

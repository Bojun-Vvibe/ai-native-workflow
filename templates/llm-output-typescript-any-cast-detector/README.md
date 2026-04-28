# llm-output-typescript-any-cast-detector

Flags `as any` and `<any>` type assertions in TypeScript source
(`.ts` / `.tsx`). Both are escape hatches that disable the type
checker for the surrounding expression.

## The smell

```ts
// src/api.ts
export async function fetchUser(id: string): Promise<{ name: string }> {
  const res = await fetch("/u/" + id);
  const body = (await res.json()) as any;            // <-- silences checker
  return { name: (body.name ?? "anon") as any };     // <-- silences checker
}
```

Once the cast is in place, `tsc` accepts whatever shape downstream code
asserts about `body`, and the next refactor ships a runtime crash that
the type system was supposed to catch.

## Why LLMs produce it

`as any` is the shortest path past a type error in training data. When
a model can't reconcile the inferred type of `await res.json()` with
the declared return type, it inserts `as any` so the snippet
"compiles". The pattern is over-represented in tutorial answers and
Stack Overflow drive-by fixes, so weakly-conditioned models default to
it instead of writing a `type` / `interface` and a runtime validator.

## Detected forms

- `expr as any`           — `as`-keyword cast.
- `<any>expr`             — angle-bracket cast (only flagged in `.ts`,
                            since `<...>` is JSX in `.tsx`).
- Variants like `as any[]`, `as any | null`, `as readonly any[]` are
  matched by the leading `as any`.

## Not flagged

- `Array<any>`, `Record<string, any>`, `Promise<any>`, `Set<any>` —
  these are *uses* of the `any` type, not casts. They deserve a separate
  detector if you care; this one focuses on the assertion form because
  that is what actually overrides inference.
- `as unknown`, `as never`, `as const`, casts to a named type.
- Mentions of `as any` or `<any>` inside string literals, template
  literals (raw text portion), or comments.
- Files in `__tests__/` directories or matching `*.test.ts`,
  `*.test.tsx`, `*.spec.ts`, `*.spec.tsx`.

## Scope details

- Template-literal interpolations (`${ ... }`) are scanned as code, so
  `as any` inside `${ x as any }` **is** flagged. Only the static text
  portion of the template is masked.
- The detector is regex-based on a comment-stripped, string-stripped
  view of the file. It does not parse TypeScript, so adversarial
  formatting can defeat it.

## Usage

```
python3 detector.py <path> [<path> ...]
```

Paths may be files or directories. Directories are walked recursively
for `*.ts` and `*.tsx` files, skipping `.git`, `node_modules`, `dist`,
and `build`.

## Exit codes

| Code | Meaning |
| ---- | ------- |
| 0    | No hits |
| 1    | One or more hits printed |
| 2    | Usage error (no path given) |

## Sample run

```
$ python3 detector.py bad/
bad/api.ts:4: `as any` cast: suppresses type checking
bad/api.ts:5: `as any` cast: suppresses type checking
bad/config.ts:3: `as any` cast: suppresses type checking
bad/config.ts:7: `as any` cast: suppresses type checking
bad/merge.ts:3: `<any>` cast: suppresses type checking
bad/merge.ts:4: `as any` cast: suppresses type checking
bad/merge.ts:9: `as any` cast: suppresses type checking
bad/cast.ts:3: `<any>` cast: suppresses type checking
bad/cast.ts:7: `<any>` cast: suppresses type checking
bad/Widget.tsx:6: `as any` cast: suppresses type checking
bad/Widget.tsx:7: `as any` cast: suppresses type checking
-- 11 hit(s)

$ python3 detector.py good/
-- 0 hit(s)
```

## Suggested fixes

- Define the actual shape and use a runtime validator (`zod`, `valibot`,
  hand-written guard).
- Use `unknown` instead of `any`, then narrow with type guards.
- Use a generic parameter to let the caller supply the type.
- If the cast is genuinely necessary at a trust boundary, prefer
  `as unknown as T` so the loss of safety is explicit and greppable,
  and document why.

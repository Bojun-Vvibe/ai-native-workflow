# llm-output-react-key-index-detector

Detects React JSX that uses an array index (`index`, `idx`, `i`, or
the loop counter from `.map((item, p) => ...)`) as the `key` prop.
This defeats React's reconciliation: when the list reorders, has
items inserted in the middle, or filters items out, React re-uses
component instances against the wrong items, leaking input state,
animation state, and effect identity. It is the single most common
React perf/correctness anti-pattern in LLM-generated tutorial code.

## Heuristic

Three checks are applied to each JSX-flavoured fence (`jsx`, `tsx`,
`js`, `ts`, `javascript`, `typescript`) or to the whole file when no
fences are found:

1. **Direct.** `key={index}`, `key={idx}`, `key={i}`.
2. **Coerced.** `key={String(index)}`, `key={\`${idx}\`}`,
   `key={i + ''}`, `key={i.toString()}`. The coercion does not
   change the underlying problem.
3. **Callback param.** `.map((item, rowNum) => ...)` followed
   (within ~40 lines) by `key={rowNum}`. The second positional
   argument to `.map` / `.forEach` / `.flatMap` / `.filter` /
   `.reduce` is captured and matched against subsequent `key={...}`
   expressions even when the variable is not literally named
   `index`.

Comments and string literals are scrubbed before matching. Template
literals are deliberately left intact so `${index}` interpolations
can be flagged.

## Usage

```
python3 detector.py path/to/file.md
python3 detector.py path/to/file.tsx
```

Findings print as `path:line:col: msg` and the script ends with
`total findings: N`.

## False-positive notes

- A `.map` callback whose second parameter is named something like
  `rowNum` will only be flagged if that name later appears inside a
  `key={...}` expression within ~40 lines of the callback opening.
  This trades a small amount of recall (long callback bodies) for a
  much lower false-positive rate.
- Fragment short syntax `<>...</>` carries no key, so it is never
  flagged.
- Static keys derived from `id`, `uuid`, `slug`, etc. are not
  flagged.
- `key={\`row-${index}\`}` (prefix + index) is *not* currently
  flagged, because it indicates the author at least thought about
  uniqueness; the index portion still has the underlying issue but
  the false-positive rate when extending the regex is too high in
  practice.
- Non-React frameworks that reuse `key=` (Vue templates, Svelte,
  SolidJS) may surface false positives. Limit the detector to JSX-
  flavoured fences when running across mixed corpora.

## Worked example

`examples/bad.md` contains five distinct uses (direct `index`,
`String()` coercion, template-literal coercion, `.toString()`
coercion, and `.map((item, rowNum) => ...)` with `key={rowNum}`).
The detector fires five findings. `examples/good.md` uses stable
ids (`item.id`) throughout and fires zero.

# llm-output-nextjs-getserversideprops-secret-leak-detector

Detect Next.js page modules where `getServerSideProps`, `getStaticProps`,
or `getInitialProps` returns a `props` object that includes a secret-
looking environment variable.

## Why

Anything returned in `props` from these data-loading functions is
serialised into the page's HTML payload (the `__NEXT_DATA__` script
tag) and shipped to every browser that hits the route. LLMs writing
Next.js pages routinely do something like:

```js
return { props: { apiKey: process.env.STRIPE_SECRET_KEY } };
```

…intending to use it server-side, but in fact leaking the secret to
every visitor. The Next.js docs are explicit: secrets in `props` are
public. Public env vars must be `NEXT_PUBLIC_*`; everything else is
server-only and must never appear in `props`.

## What it flags

A line inside a `getServerSideProps` / `getStaticProps` /
`getInitialProps` function body (detected via brace-depth scan from the
`export … function get…(`/`export … const get… =`/`function get…(`
declaration) where the returned `props` object contains a key whose
value is `process.env.<NAME>` and `<NAME>` looks like a secret:

- contains `SECRET`, `KEY`, `TOKEN`, `PASSWORD`, `PASS`, `PRIVATE`,
  `CREDENTIAL`, `DSN`, `WEBHOOK`, `SIGNING`, `SALT`, or `API_KEY`
  (case-insensitive), AND
- does NOT start with `NEXT_PUBLIC_` (those are intentionally public).

Also flags spread shapes where the entire `process.env` is splatted
into props:

```js
return { props: { ...process.env } };
```

## What it does NOT flag

- `NEXT_PUBLIC_*` env vars (designed to be public).
- Secret env vars used outside the props return (e.g. fetched server-
  side and the *result* returned).
- Lines suffixed with `// next-secret-ok`.
- Files that don't contain a `getServerSideProps` /
  `getStaticProps` / `getInitialProps` declaration at all.

## Usage

```bash
python3 detect.py path/to/pages
```

Exit 1 on findings, 0 otherwise. Pure python3 stdlib. Walks `.js`,
`.jsx`, `.ts`, `.tsx` files.

## Worked example

```bash
./verify.sh
```

Should print `PASS` with `bad findings: >=5` and `good findings: 0`.

## Suppression

Append `// next-secret-ok` to the offending line if the value is
intentionally public despite the suspicious name.

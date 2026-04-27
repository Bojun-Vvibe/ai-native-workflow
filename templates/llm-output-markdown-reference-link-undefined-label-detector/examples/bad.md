# Bad example — undefined reference labels

LLMs often emit reference-style links and forget to add the definition at the
bottom of the document.

See [the docs][docs-link] for setup instructions, and the [API reference][api]
for endpoint details. The collapsed form [Quickstart Guide][] also breaks here.

An image with a missing definition: ![architecture diagram][arch-fig].

Inline `code [not-a-link][not-checked]` is ignored.

Only one valid definition exists below:

[docs-link]: https://example.com/docs

```
Inside a fence: [also-ignored][nope] should not trigger.
```

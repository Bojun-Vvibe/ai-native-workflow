# llm-output-mattermost-enable-developer-true-detector

Detect Mattermost server configurations that LLMs commonly emit
with `ServiceSettings.EnableDeveloper` and/or
`ServiceSettings.EnableTesting` set to `true`. Both flags are dev-only
according to the Mattermost handbook:

- `EnableDeveloper: true` surfaces unhandled JavaScript exceptions to
  every connected client and exposes verbose stack traces in the UI.
- `EnableTesting: true` mounts the `/api/v4/test/*` routes
  (`test/email`, `test/site_url`, `test/url`) which act as
  unauthenticated SSRF primitives: the server issues arbitrary
  outbound HTTP requests on the caller's behalf to verify
  reachability.

When asked "give me a Mattermost `config.json`" or "set up Mattermost
for testing", models routinely flip both flags to `true` and forget
to flip them back for production. They also emit the documented
env-var overrides (`MM_SERVICESETTINGS_ENABLEDEVELOPER=true`) and the
`mmctl config set` form with the same defect.

## Bad patterns

1. `config.json`-style JSON with a `ServiceSettings` object containing
   `"EnableDeveloper": true` or `"EnableTesting": true`.
2. Environment-variable form: `MM_SERVICESETTINGS_ENABLEDEVELOPER=true`
   or `MM_SERVICESETTINGS_ENABLETESTING=true`.
3. CLI override: `mattermost ... -ServiceSettings.EnableDeveloper=true`
   or `mmctl config set ServiceSettings.EnableTesting true`.

## Good patterns

- The same configs with both fields explicitly `false`.
- Configs that do not contain `ServiceSettings` at all.
- CLI invocations that read or query rather than set those fields.

## Tests

```sh
./detect.sh samples/bad/* samples/good/*
```

Exit 0 iff every bad sample is flagged AND no good sample is.

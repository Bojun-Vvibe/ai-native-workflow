# llm-output-directus-admin-default-credentials-detector

Static detector for Directus deployments whose **bootstrap admin
account** uses a documented upstream default email or password.

## Why

The Directus quickstart docs and the official `directus/directus`
container image both ship with placeholder bootstrap credentials:

```
ADMIN_EMAIL=admin@example.com
ADMIN_PASSWORD=d1r3ctu5
```

Operators commonly copy the snippet verbatim into `docker-compose.yml`,
`.env`, or a Helm values file and never rotate it. Once the container
runs `npx directus bootstrap`, that pair becomes a permanent
super-admin login on the public app instance.

This detector flags four shapes:

1. `docker-compose.yml` env block where `ADMIN_EMAIL` is one of the
   known upstream literals (`admin@example.com`, `admin@admin.com`)
   **or** `ADMIN_PASSWORD` is one of the known weak literals
   (`d1r3ctu5`, `directus`, `admin`, `password`, `changeme`).
2. `.envfile` style files setting the same vars to the same values.
3. Helm values / kubernetes manifest snippets with `adminEmail:` /
   `adminPassword:` set to the defaults.
4. Shell snippets exporting `ADMIN_EMAIL=` / `ADMIN_PASSWORD=` to a
   weak literal before invoking `directus bootstrap`.

## When to use

- Reviewing LLM-emitted Directus install snippets before applying.
- Pre-merge gate on `infra/cms/**` or `apps/directus/**` config repos.
- Spot check on container image build scripts and Helm chart values.

## Suppression

Same line or the line directly above:

```
# directus-admin-default-credentials-allowed
```

Use sparingly — typically only for ephemeral local-dev compose
overrides on a loopback bind that will be rotated immediately
after first login.

## How to run

```sh
./verify.sh
```

This runs `detector.py` against every fixture under `examples/bad`
and `examples/good` and prints a `bad=N/N good=0/N PASS` summary.

## Direct invocation

```sh
python3 detector.py path/to/docker-compose.yml
```

Exit code is the number of files with at least one finding (capped
at 255). Stdout lines are formatted `<file>:<line>:<reason>`.

## Limitations

- The detector only looks at common config surfaces. A Directus
  instance bootstrapped via the SDK or via a runtime API call after
  startup is not in scope.
- Password strength beyond the weak-literal denylist is not
  evaluated; a custom but still weak password (e.g. `Passw0rd`) will
  not be flagged.

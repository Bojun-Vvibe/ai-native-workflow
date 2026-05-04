# llm-output-jupyterhub-dummy-authenticator-detector

Detects `jupyterhub_config.py` files that wire the
`DummyAuthenticator` (every login succeeds, with any password) on a
hub that is reachable from a non-loopback interface.

## Why this matters

JupyterHub's `DummyAuthenticator` ships in the `dummyauthenticator`
package and is also re-exported by JupyterHub itself for testing.
Setting:

    c.JupyterHub.authenticator_class = 'dummy'

means *any* username with *any* password is accepted, and that user
gets a single-user notebook server with arbitrary code execution on
the hub host. JupyterHub's default `JupyterHub.ip = ''` binds to all
interfaces, so a freshly written `jupyterhub_config.py` that pastes
the dummy authenticator from the docs is a remote-code-execution
service on `:8000` for anyone who can route to it.

LLM-generated JupyterHub setups frequently emit this pattern because
it is the shortest snippet in the upstream "Quickstart" guide.

## What it detects

For each scanned `jupyterhub_config.py`, the detector reports a
finding when:

1. There is an assignment to `c.JupyterHub.authenticator_class` whose
   right-hand side resolves to the dummy authenticator. Recognised
   forms:
   - `'dummy'` (JupyterHub's built-in entry point name)
   - `'dummyauthenticator.DummyAuthenticator'`
   - `'jupyterhub.auth.DummyAuthenticator'`
   - bare class reference `DummyAuthenticator` (with `from
     dummyauthenticator import DummyAuthenticator`)
2. AND the hub binds beyond loopback. This is true when:
   - `c.JupyterHub.ip` is unset (default is all interfaces), OR
   - `c.JupyterHub.ip` is a non-loopback address, OR
   - `c.JupyterHub.bind_url` host part is non-loopback.

## CWE references

- CWE-287: Improper Authentication
- CWE-489: Active Debug Code (test authenticator in production)
- CWE-306: Missing Authentication for Critical Function

## False-positive surface

- `c.JupyterHub.ip = '127.0.0.1'` (or `'::1'` / `'localhost'`) is
  treated as a dev sandbox and ignored.
- A `bind_url` whose host is loopback is ignored.
- A file that intentionally documents the dummy authenticator (e.g.
  a hardening tutorial showing the BAD example) can be suppressed
  with a top-of-file comment `# jupyterhub-dummy-auth-allowed`.

## Usage

    python3 detector.py path/to/jupyterhub_config.py

Exit code: number of files with at least one finding (capped at 255).
Stdout format: `<file>:<line>:<reason>`.

Run `bash verify.sh` to execute the bundled good/bad fixtures.

## Worked example

Real, captured output from `bash verify.sh` against the bundled
fixtures:

    bad=4/4 good=0/4
    PASS

Per-fixture detector output (`python3 detector.py examples/bad/*`):

    01_dummy_string_all_ifaces.py:3:JupyterHub DummyAuthenticator wired (authenticator_class='dummy'); accepts any username/password on bind=0.0.0.0
    02_dummy_dotted_bind_url.py:2:JupyterHub DummyAuthenticator wired (authenticator_class="dummyauthenticator.DummyAuthenticator"); accepts any username/password on bind=0.0.0.0
    03_class_import_default_bind.py:4:JupyterHub DummyAuthenticator wired (authenticator_class=DummyAuthenticator); accepts any username/password on bind=<default 0.0.0.0>
    04_dummy_public_ip.py:2:JupyterHub DummyAuthenticator wired (authenticator_class='dummy'); accepts any username/password on bind=192.0.2.42

The good fixtures all return exit 0 with no output: PAM authenticator,
loopback-bound dummy, OAuth (GitHub), and the suppressed hardening
tutorial.

## LLM-output detection prompt

When reviewing LLM-generated `jupyterhub_config.py`, flag any output
that sets `c.JupyterHub.authenticator_class` to `'dummy'`,
`'dummyauthenticator.DummyAuthenticator'`, or a bare
`DummyAuthenticator` class reference unless the same file pins
`c.JupyterHub.ip` (or the host part of `bind_url`) to loopback. The
dummy authenticator is a test stub — an exposed hub using it is an
unauthenticated notebook server with shell access for every visitor.

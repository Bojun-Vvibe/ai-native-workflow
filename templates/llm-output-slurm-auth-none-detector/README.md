# llm-output-slurm-auth-none-detector

Detects Slurm Workload Manager configurations (`slurm.conf`) that
disable RPC authentication by setting `AuthType=auth/none`.

## What it flags

Any uncommented assignment of the form:

```
AuthType=auth/none
```

(case-insensitive on the key, with optional whitespace around `=`).
Also flags the explicit equivalent `AuthType = none`.

The detector ignores commented lines (`#` to end of line) and ignores
secure values such as `auth/munge` and `auth/jwt`.

## Why it's bad

Slurm's `slurmctld`, `slurmd` and `slurmdbd` daemons authenticate every
RPC using a credential plugin selected by `AuthType`. The default and
recommended value is `auth/munge` (or `auth/jwt` for token flows),
which signs each RPC with a shared cluster secret.

`auth/none` disables all authentication — any host that can reach the
controller's TCP port can submit jobs as any user (including root via
`--uid=0`), cancel jobs, mutate partitions, drain nodes, and on a
cluster with shared filesystems read or overwrite any user's data via a
crafted job. Multiple public exploit write-ups document trivial cluster
takeover when `auth/none` is left on a network-reachable controller.

`auth/none` is documented in the Slurm manual as **only** appropriate
for an isolated single-user development cluster, and even there it is
discouraged.

## References

- `slurm.conf(5)` — `AuthType` parameter
  <https://slurm.schedmd.com/slurm.conf.html#OPT_AuthType>
- Slurm Quick Start Administrator Guide — Authentication section
  <https://slurm.schedmd.com/quickstart_admin.html#auth>
- MUNGE project (default credential backend)
  <https://github.com/dun/munge>

## Usage

```
./detect.py path/to/slurm.conf
cat slurm.conf | ./detect.py -
```

Exit status:
- `0` — no insecure assignment found
- `1` — at least one offending line; `file:line:` location printed
- `2` — usage error

## Limitations

- Only inspects the file passed on the command line; it does not follow
  Slurm's `Include` directive.
- Does not validate that a non-`none` `AuthType` is actually reachable
  (e.g. that MUNGE is running) — that is a runtime concern.
- Does not flag missing `AuthType` lines. Slurm's compiled-in default
  is `auth/munge`, so absence is treated as safe.

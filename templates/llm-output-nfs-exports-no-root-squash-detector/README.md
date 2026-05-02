# llm-output-nfs-exports-no-root-squash-detector

Detects LLM-generated `/etc/exports` (Linux NFS server) entries that
disable root-squashing while exporting to the world (or to a wide
subnet) — an export shape that lets any client UID 0 act as the server's
UID 0 against the exported tree.

## Why this matters

`no_root_squash` tells the NFS server to **trust the client's root
account**. Combined with a permissive client spec (`*`, `0.0.0.0/0`,
`::/0`, or wide CIDR ranges like `10.0.0.0/8` for an internet-exposed
host) this is equivalent to giving every reachable host root on the
exported filesystem. The standard exploitation path is:

1. Mount the export from any attacker-controlled box.
2. `chown 0:0` a SUID-root binary into the export.
3. Re-enter through any other client and execute it.

The Linux `exports(5)` default is `root_squash`; LLM output regularly
overrides it with snippets like `/srv/nfs *(rw,no_root_squash)` because
that string appears in countless StackOverflow answers about "fixing
permission errors".

## What this checks

For each input file the detector flags any export line where:

* The option list contains `no_root_squash`, **and**
* At least one client spec is "wide": literal `*`, `0.0.0.0/0`,
  `::/0`, `0.0.0.0`, `::`, or a CIDR with prefix length `<= 16` (IPv4)
  / `<= 32` (IPv6).

It additionally flags any line with `no_all_squash` + `insecure` + a
wide client spec, because that combination preserves attacker-supplied
UIDs from non-privileged source ports — same outcome by a longer route.

Output: `<file>:<line>:<reason>` per offending export. Exit code =
number of files with at least one finding (capped at 255).

## False-positive surface

* Lines whose client spec is purely loopback (`127.0.0.1`,
  `localhost`, `::1`) are ignored even with `no_root_squash`.
* Files containing the marker `# nfs-no-root-squash-allowed` on any
  line are skipped (e.g. trusted single-tenant lab fixtures).
* Comments and blank lines are ignored.
* Multi-client lines (`/srv host1(rw) host2(rw,no_root_squash)`) are
  parsed per client spec, so a tight client with `no_root_squash`
  next to a wide client without it does **not** falsely fire.

## CWE refs

* CWE-732: Incorrect Permission Assignment for Critical Resource
* CWE-269: Improper Privilege Management
* CWE-284: Improper Access Control

## Usage

```sh
python3 detector.py path/to/exports [more ...]
./verify.sh   # runs against bundled fixtures, prints PASS/FAIL
```

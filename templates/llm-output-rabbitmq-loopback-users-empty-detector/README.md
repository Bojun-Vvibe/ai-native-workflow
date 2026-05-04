# llm-output-rabbitmq-loopback-users-empty-detector

Detects RabbitMQ configurations that clear the `loopback_users` list,
re-enabling the default `guest` user for remote connections — the
exact shape that LLM "I can't connect to RabbitMQ from another host
with guest/guest, fix it" snippets emit.

## Why this matters

RabbitMQ ships with a built-in administrator `guest` whose password
is also `guest`. Since 3.3.0 the broker restricts that account to
loopback connections via `loopback_users` (default
`[<<"guest">>]`). The whole reason that restriction exists is that
the credentials are public knowledge — anyone scanning 5672 / 5671
will try `guest:guest` first.

When users hit `ACCESS_REFUSED - Login was refused using
authentication mechanism PLAIN` from a remote host and ask an
assistant to fix it, the canonical wrong answer is one of:

* `{loopback_users, []}` — classic Erlang-term `rabbitmq.config` /
  `advanced.config`
* `loopback_users.guest = none` — newer sysctl-style `rabbitmq.conf`
* `loopback_users =` (empty) — same intent, different syntax

Any of those turns `guest:guest` into a remotely usable administrator
on the default vhost. Vhost permissions for `guest` are
`".*" ".*" ".*"` by default — full configure / write / read on every
queue and exchange.

## Rules

A finding is emitted when ANY of:

1. **Erlang term form.** `{loopback_users, []}` appears anywhere in
   the file (whitespace-tolerant, multi-line tolerant).
2. **sysctl/.conf form.** A line of the form
   `loopback_users[.<idx>] = none` (case-insensitive). The literal
   `none` is the documented way to clear the list in `rabbitmq.conf`.
3. **sysctl/.conf empty.** A line `loopback_users[.<idx>] =` with
   an empty value.

A line containing the marker `# rabbitmq-loopback-cleared-allowed`
(or the Erlang-comment variant `% rabbitmq-loopback-cleared-allowed`)
suppresses the finding for the whole file. Use only when a separate
provisioner deletes the `guest` user on boot — a fact this static
check cannot see.

## Out of scope

* Other built-in default credentials (e.g. management plugin's
  default admin if recreated by Helm chart values).
* `default_user` / `default_pass` overrides that change `guest` to
  another weak password — that is a separate misconfig pattern.
* AMQPS / TLS misconfig.

## Run

```
python3 detector.py examples/bad/01_classic_erlang_empty_list.config
./verify.sh
```

`verify.sh` exits 0 when the detector flags 4/4 bad and 0/4 good.

## Verified output

```
$ ./verify.sh
bad=4/4 good=0/4
PASS

$ python3 detector.py examples/bad/01_classic_erlang_empty_list.config
examples/bad/01_classic_erlang_empty_list.config:4:RabbitMQ {loopback_users, []} clears the loopback-only restriction on the default 'guest' user — guest:guest becomes a remotely usable administrator

$ python3 detector.py examples/bad/02_whitespace_erlang_form.config
examples/bad/02_whitespace_erlang_form.config:5:RabbitMQ {loopback_users, []} clears the loopback-only restriction on the default 'guest' user — guest:guest becomes a remotely usable administrator

$ python3 detector.py examples/bad/03_sysctl_none_form.conf
examples/bad/03_sysctl_none_form.conf:3:RabbitMQ loopback_users = none clears the loopback-only restriction on the default 'guest' user — guest:guest becomes a remotely usable administrator

$ python3 detector.py examples/bad/04_sysctl_empty_form.conf
examples/bad/04_sysctl_empty_form.conf:3:RabbitMQ loopback_users = <empty> clears the loopback-only restriction on the default 'guest' user — guest:guest becomes a remotely usable administrator

$ for f in examples/good/*; do python3 detector.py "$f"; done
$  # (no output, exit 0 each — all four are correctly silent)
```

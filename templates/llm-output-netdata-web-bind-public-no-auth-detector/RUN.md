# RUN.md — actual exec output

```
$ ./detect.sh fixtures/bad/01-wildcard-bind.netdata.conf
FAIL: fixtures/bad/01-wildcard-bind.netdata.conf: [web] public bind '*' with allow-from '*' and no bearer-token gate
(exit=1)

$ ./detect.sh fixtures/bad/02-zero-bind-default-acl.netdata.conf
FAIL: fixtures/bad/02-zero-bind-default-acl.netdata.conf: [web] public bind '0.0.0.0' with allow-from '*' and no bearer-token gate
(exit=1)

$ ./detect.sh fixtures/bad/03-public-ipv4-bind.netdata.conf
FAIL: fixtures/bad/03-public-ipv4-bind.netdata.conf: [web] public bind '203.0.113.10' with allow-from '*' and no bearer-token gate
(exit=1)

$ ./detect.sh fixtures/bad/04-ipv6-any-explicit-no-bearer.netdata.conf
FAIL: fixtures/bad/04-ipv6-any-explicit-no-bearer.netdata.conf: [web] public bind '::' with allow-from '*' and no bearer-token gate
(exit=1)

$ ./detect.sh fixtures/good/01-loopback-only.netdata.conf
PASS: fixtures/good/01-loopback-only.netdata.conf
(exit=0)

$ ./detect.sh fixtures/good/02-web-disabled.netdata.conf
PASS: fixtures/good/02-web-disabled.netdata.conf
(exit=0)

$ ./detect.sh fixtures/good/03-bearer-protected.netdata.conf
PASS: fixtures/good/03-bearer-protected.netdata.conf
(exit=0)

$ ./detect.sh fixtures/good/04-loopback-list.netdata.conf
PASS: fixtures/good/04-loopback-list.netdata.conf
(exit=0)

```

Summary: bad=4/4 detected, good=0/4 false positives.

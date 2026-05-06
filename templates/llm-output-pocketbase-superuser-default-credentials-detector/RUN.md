# RUN.md — actual exec output

```
$ ./detect.sh fixtures/bad/01-entrypoint-shell.sh
FAIL: fixtures/bad/01-entrypoint-shell.sh: pocketbase superuser bootstrap with default email 'admin@example.com' + weak/default password -> ./pocketbase superuser upsert admin@example.com 1234567890
(exit=1)

$ ./detect.sh fixtures/bad/02-dockerfile-cmd.Dockerfile
FAIL: fixtures/bad/02-dockerfile-cmd.Dockerfile: pocketbase superuser bootstrap with default email 'test@test.com' + weak/default password -> RUN /pb/pocketbase superuser create test@test.com password
(exit=1)

$ ./detect.sh fixtures/bad/03-compose-command.yml
FAIL: fixtures/bad/03-compose-command.yml: pocketbase superuser bootstrap with default email 'admin@admin.com' + weak/default password ->       sh -c "pocketbase admin create admin@admin.com changeme &&
(exit=1)

$ ./detect.sh fixtures/bad/04-go-bootstrap.go
FAIL: fixtures/bad/04-go-bootstrap.go: programmatic admin bootstrap with weak/default password 'password123' -> 		admin.SetPassword("password123")
(exit=1)

$ ./detect.sh fixtures/good/01-entrypoint-from-env.sh
PASS: fixtures/good/01-entrypoint-from-env.sh
(exit=0)

$ ./detect.sh fixtures/good/02-strong-literal.sh
PASS: fixtures/good/02-strong-literal.sh
(exit=0)

$ ./detect.sh fixtures/good/03-no-bootstrap.Dockerfile
PASS: fixtures/good/03-no-bootstrap.Dockerfile
(exit=0)

$ ./detect.sh fixtures/good/04-go-from-env.go
PASS: fixtures/good/04-go-from-env.go
(exit=0)

```

Summary: bad=4/4 detected, good=0/4 false positives.

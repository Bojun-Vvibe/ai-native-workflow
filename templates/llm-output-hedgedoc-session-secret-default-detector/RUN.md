# RUN.md — actual exec output

```
$ shellcheck -e SC2094 detect.sh && echo CLEAN
CLEAN

$ ./detect.sh fixtures/bad/01-literal-secret.envtxt
FAIL: fixtures/bad/01-literal-secret.envtxt: CMD_SESSION_SECRET is too short (6 chars) -> CMD_SESSION_SECRET=secret
(exit=1)

$ ./detect.sh fixtures/bad/02-empty.envtxt
FAIL: fixtures/bad/02-empty.envtxt: CMD_SESSION_SECRET is empty -> CMD_SESSION_SECRET=
(exit=1)

$ ./detect.sh fixtures/bad/03-changeme-quoted.envtxt
FAIL: fixtures/bad/03-changeme-quoted.envtxt: CMD_SESSION_SECRET is too short (8 chars) -> CMD_SESSION_SECRET="changeme"
(exit=1)

$ ./detect.sh fixtures/bad/04-config.json
FAIL: fixtures/bad/04-config.json: sessionSecret is too short (15 chars) ->     "sessionSecret": "PleaseChangeMe",
(exit=1)

$ ./detect.sh fixtures/good/01-strong-random.envtxt
PASS: fixtures/good/01-strong-random.envtxt
(exit=0)

$ ./detect.sh fixtures/good/02-with-comments.envtxt
PASS: fixtures/good/02-with-comments.envtxt
(exit=0)

$ ./detect.sh fixtures/good/03-config.json
PASS: fixtures/good/03-config.json
(exit=0)

$ ./detect.sh fixtures/good/04-single-quoted.envtxt
PASS: fixtures/good/04-single-quoted.envtxt
(exit=0)

```

Summary: bad=4/4 detected, good=0/4 false positives.

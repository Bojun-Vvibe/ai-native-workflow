# RUN.md — actual exec output

```
$ shellcheck -e SC2094 detect.sh && echo CLEAN
CLEAN

$ ./detect.sh fixtures/bad/01-upstream-placeholder.envtxt
FAIL: fixtures/bad/01-upstream-placeholder.envtxt: SYMFONY__ENV__SECRET matches known placeholder 'ThisTokenIsNotSoSecretChangeIt' -> SYMFONY__ENV__SECRET=ThisTokenIsNotSoSecretChangeIt
(exit=1)

$ ./detect.sh fixtures/bad/02-empty.envtxt
FAIL: fixtures/bad/02-empty.envtxt: SYMFONY__ENV__SECRET is empty -> SYMFONY__ENV__SECRET=
(exit=1)

$ ./detect.sh fixtures/bad/03-changeme-quoted.envtxt
FAIL: fixtures/bad/03-changeme-quoted.envtxt: SYMFONY__ENV__SECRET is too short (8 chars) -> SYMFONY__ENV__SECRET="changeme"
(exit=1)

$ ./detect.sh fixtures/bad/04-parameters.yml
FAIL: fixtures/bad/04-parameters.yml: SYMFONY__ENV__SECRET matches known placeholder 'ThisTokenIsNotSoSecretChangeIt' ->     secret: ThisTokenIsNotSoSecretChangeIt
(exit=1)

$ ./detect.sh fixtures/good/01-strong-random.envtxt
PASS: fixtures/good/01-strong-random.envtxt
(exit=0)

$ ./detect.sh fixtures/good/02-hex-rand.envtxt
PASS: fixtures/good/02-hex-rand.envtxt
(exit=0)

$ ./detect.sh fixtures/good/03-parameters.yml
PASS: fixtures/good/03-parameters.yml
(exit=0)

$ ./detect.sh fixtures/good/04-with-comments.envtxt
PASS: fixtures/good/04-with-comments.envtxt
(exit=0)

```

Summary: bad=4/4 detected, good=0/4 false positives.

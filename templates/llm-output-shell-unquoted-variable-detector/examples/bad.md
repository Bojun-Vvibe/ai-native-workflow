# bad.md — 6 intentional findings

Inline:

```bash
#!/usr/bin/env bash
dir=/tmp/scratch
rm -rf $dir/build              # finding 1: unquoted_var $dir
cp $src $dst                   # findings 2 & 3: unquoted_var $src, $dst
echo $(whoami) is here         # finding 4: unquoted_cmdsub $(whoami)
greeting="hello ${name}"       # safe (inside double quotes)
echo "user: ${USER}"           # safe (inside double quotes)
for f in ${files}; do          # finding 5: unquoted_var ${files}
  : "$f"
done
log=/var/log/app.log           # safe assignment
tail -n 20 ${log}              # finding 6: unquoted_var ${log}
```

A heredoc body that should NOT be scanned (any `$x` inside is body
text):

```sh
cat <<EOF
hello $world this is heredoc body, ignored
EOF
```

Comments are skipped:

```bash
# echo $not_a_finding
```

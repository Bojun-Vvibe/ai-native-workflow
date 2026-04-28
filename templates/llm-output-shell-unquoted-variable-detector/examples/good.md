# good.md — 0 findings

All expansions are quoted, or are bare assignments, or are special
parameters.

```bash
#!/usr/bin/env bash
dir=/tmp/scratch
rm -rf "$dir/build"
cp "$src" "$dst"
echo "$(whoami) is here"
greeting="hello ${name}"
echo "user: ${USER}"
for f in "${files[@]}"; do
  : "$f"
done
log=/var/log/app.log
tail -n 20 "${log}"
echo "exit=$?"
echo "pid=$$"
echo "args=$#"
```

Heredoc body is skipped regardless:

```sh
cat <<EOF
hello $world this is heredoc body, ignored
EOF
```

Non-shell fence is ignored entirely:

```python
x = "$dollar in python is fine"
```

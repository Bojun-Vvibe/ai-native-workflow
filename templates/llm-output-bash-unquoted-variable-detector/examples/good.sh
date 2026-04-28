#!/usr/bin/env bash
# Good: same script as bad.sh but every expansion that could split is
# quoted, and we use [[ ]] for the test. Detector should report zero
# findings.

set -e

SRC=$1                            # whitelisted: simple VAR=$other
DST=$2                            # whitelisted: simple VAR=$other

cp -- "$SRC" "$DST"

echo "Found: $(find . -name '*.txt' | head -1)"   # inside double quotes

NAME="${USER_NAME}"
if [[ -n $NAME ]]; then           # inside [[ ]] -- no splitting
    echo "hi $NAME"
fi

# Iterate over a glob, not over $(ls ...). And quote $f.
for f in "$SRC"/*; do
    echo "processing $f"
done

HOST="$(hostname)"
echo "connecting to $HOST"

cat > "$DST/log.txt" <<EOF
hello world
EOF

# Arithmetic context -- $i is fine unquoted.
i=0
while (( i < 3 )); do
    i=$(( i + 1 ))
done

# Numeric specials -- not flagged.
echo "exit was $?"
echo "pid is $$"

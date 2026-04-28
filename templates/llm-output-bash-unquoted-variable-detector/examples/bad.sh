#!/usr/bin/env bash
# Bad: unquoted expansions everywhere. Each one breaks on a path with
# a space, a glob char, or an empty value.

set -e

SRC=$1
DST=$2

# FINDING 1+2: $SRC and $DST unquoted in cp args
cp $SRC $DST

# FINDING 3: command substitution unquoted
echo Found: $(find . -name '*.txt' | head -1)

# FINDING 4: ${BRACED} unquoted in test
NAME=${USER_NAME}
if [ -n $NAME ]; then
    echo hi $NAME            # FINDING 5: $NAME unquoted in echo args
fi

# FINDING 6: unquoted glob result
for f in $(ls $SRC); do      # FINDING 7: $SRC again, in $(...)
    echo processing $f       # FINDING 8: $f unquoted
done

# Backtick form, also flagged
HOST=`hostname`
echo connecting to $HOST     # FINDING 9: $HOST unquoted

# Redirection target unquoted
cat > $DST/log.txt <<EOF
hello world
EOF
# FINDING 10: $DST in redirection target above

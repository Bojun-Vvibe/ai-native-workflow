# Test cases for double-backtick misuse

Use the ``foo`` function to do the thing.

The ``--verbose`` flag enables it.

Here is a clean single-backtick: `bar` — fine.

This one ``has multiple words`` and still no backtick inside.

Required double form: ``foo`bar`` — must NOT flag (content has backtick).

Empty span: `` `` — must NOT flag (whitespace-only).

Triple-backtick span ```triple``` is out of scope.

Mixed: leading ``alpha`` then `beta` then ``gamma`` on one line.

A run with leading/trailing space inside double: ``  spaced  `` — flag with trim suggestion.

```
Inside fence: ``not flagged`` because fence is skipped wholesale.
Another: ``also-not-flagged``.
```

After fence: ``after-fence-flagged``.

Code with only backtick content: `` ` `` — must NOT flag (content is a single backtick).

Multi-line spans are out of scope so this opening ``does
not close on this line`` should not be matched as a single span.

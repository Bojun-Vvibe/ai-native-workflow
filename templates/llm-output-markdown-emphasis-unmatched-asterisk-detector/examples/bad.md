# Bad sample

This sentence has *unmatched emphasis that runs off the line.

A line with *one good* pair and an *extra opener.

Even **strong** can go wrong: **opened twice ** and not paired *.

End of bad sample (note the lone trailing asterisk).

The fenced block below contains the offending pattern as code; it
must NOT trigger:

```text
This *has unmatched emphasis* but **only one bold and a stray *.
```

A list with valid emphasis, no false positive expected:

* item one with *good* emphasis
* item two with **good** strong

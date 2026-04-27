# Overview.

This document is a worked example for the trailing-punctuation-in-heading
detector.

## Why this matters!

Every heading above ends with disallowed punctuation.

### Background:

Some background prose follows.

#### A clean heading

This one is fine and should not be flagged.

##### Are we done?

Question marks are also flagged.

###### Final note,

Trailing comma — also flagged.

Setext heading with period.
===========================

Some prose under the setext h1.

Another setext heading;
-----------------------

More prose.

Clean setext heading
====================

This setext heading is fine.

## Closing thoughts

No trailing punctuation here, so this one is clean.

```
# Heading inside fence.
## Another fenced heading!
```

The two lines inside the fenced code block above must NOT be flagged.

# Sample doc with planted heading-trailing-punctuation findings

## Why this matters.

Good prose follows. The heading above ends with a period.

### Conclusion!

An exclamation on a heading reads as marketing copy.

#### Open questions?

Question marks on headings are common in LLM blog drafts.

##### Closing hashes too. ##

The trailing `##` is stripped before the period check.

###### v1.0.

Even abbreviation-style trailing periods are flagged at heading
position — the right fix is to drop the period.

## Clean heading

This one is fine and should not be flagged.

## Slide-style heading…

Ellipsis ending is intentional and NOT flagged.

## Three-dot ellipsis...

ASCII three-dot ellipsis is also NOT flagged.

Now a fenced block that demonstrates bad headings — must be
skipped:

```
## Inside fence with period.
### Inside fence with bang!
```

After the fence, this should fire again:

## Trailing period after fence.

And tilde fences too:

~~~
#### Skipped tilde fence.
~~~

## Heading with trailing spaces.   

Trailing spaces are stripped before the punctuation check, so
this still fires.

Negative case — not actually a heading because no space after `#`:

#NotAHeading.

Negative case — too many hashes (7) is not a valid ATX heading:

####### TooDeep.

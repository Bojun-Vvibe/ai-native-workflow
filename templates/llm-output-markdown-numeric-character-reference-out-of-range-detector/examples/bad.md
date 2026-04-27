# bad numeric character references

Above the Unicode max: &#x110000; should not parse.

Surrogate half: &#xD800; is reserved for UTF-16.

NULL byte: &#0; renders as U+FFFD.

Emoji typo (extra hex digit): &#x1F6000; was meant to be U+1F600.

These are all fine: &#x1F600; (smiley), &#65; (A), &#x2603; (snowman).

Inline code with a deliberately bad reference is ignored: `&#x110000;`.

Inside a fence the bad references are also ignored:

```
&#x110000;
&#xD800;
&#0;
```

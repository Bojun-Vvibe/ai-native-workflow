# clean numeric character references

Smiley emoji: &#x1F600;.

Capital A: &#65;.

Snowman: &#x2603;.

Padded decimal (still in range): &#000065;.

Maximum legal code point: &#x10FFFF;.

Inline code with deliberately bad references: `&#x110000;` and `&#xD800;`.

Fenced code with bad references must be ignored:

```
&#x110000;
&#xD800;
&#0;
```

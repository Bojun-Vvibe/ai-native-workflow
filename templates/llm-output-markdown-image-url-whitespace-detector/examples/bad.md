# bad images

![diagram](assets/system diagram.png)

![figure](images/figure 2.svg)

![tabbed](a	b.png)

This one is fine: ![ok](assets/system-diagram.png)

This one is also fine (encoded space): ![ok2](assets/system%20diagram.png)

This one is fine (quoted title is allowed after the URL): ![ok3](assets/img.png "a title with spaces")

Inline code with a deliberately bad image is ignored: `![x](a b.png)`

Inside a fence the bad image is also ignored:

```
![y](a b.png)
```

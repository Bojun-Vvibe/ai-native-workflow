# Clean nesting patterns

Outer fence is 4 backticks; inner is 3:

````
```
print("inner")
```
````

Outer is backticks; inner is tildes:

```
~~~
echo nested
~~~
```

Two unrelated blocks with prose between them (gap > 3 lines):

```
block one
```

Then several lines of prose here.
And more prose.
And still more prose.
And yet another line of prose so the gap is large enough.

```
block two
```

A single fenced block followed by prose:

```
only block
```

The end.

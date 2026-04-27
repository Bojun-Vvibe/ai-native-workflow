# A clean markdown sample.

Code blocks with proper info strings:

```python
print("hello")
```

```json
{"k": 1}
```

~~~bash
echo hi
~~~

```yaml
key: value
```

Empty info string is fine — nothing to trim:

```
plain text block
```

Long fence, also clean:

````diff
- old
+ new
````

Inline mention of ```` ``` ```` with surrounding text shouldn't trigger anything.

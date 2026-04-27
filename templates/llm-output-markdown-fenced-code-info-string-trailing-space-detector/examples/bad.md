# A bad markdown sample with trailing whitespace on fenced-code info strings.

The first block has a trailing space after `python`:

```python 
print("hello")
```

And another block has a tab after `json`:

```json	
{"k": 1}
```

Mixed tilde fence, also bad — two trailing spaces after `bash`:

~~~bash  
echo hi
~~~

A clean opener (no trailing space) — should NOT be flagged:

```yaml
key: value
```

Final bad case: long fence with info-string trailing space.

````diff 
- old
+ new
````

# Smoke test

```
$ python3 detector.py bad/
bad/05_unpickler.py:7: unsafe pickle deserialization via pickle.<call>: untrusted bytes => arbitrary code execution
bad/04_from_import.py:5: unsafe pickle deserialization via loads(...): untrusted bytes => arbitrary code execution
bad/03_alias.py:5: unsafe pickle deserialization via p.<call>: untrusted bytes => arbitrary code execution
bad/01_pickle_load.py:6: unsafe pickle deserialization via pickle.<call>: untrusted bytes => arbitrary code execution
bad/02_pickle_loads.py:5: unsafe pickle deserialization via pickle.<call>: untrusted bytes => arbitrary code execution
-- 5 hit(s)
```

```
$ python3 detector.py good/
-- 0 hit(s)
```

5 / 0 — passing.

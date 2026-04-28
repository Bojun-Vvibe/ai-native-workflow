# Smoke test

```
$ python3 detector.py bad/
bad/05_nested.go:16: defer inside for-loop: resource released only at function return
bad/04_http.go:11: defer inside for-loop: resource released only at function return
bad/01_basic_open.go:11: defer inside for-loop: resource released only at function return
bad/03_mutex.go:8: defer inside for-loop: resource released only at function return
bad/02_db_rows.go:13: defer inside for-loop: resource released only at function return
-- 5 hit(s)
```

```
$ python3 detector.py good/
-- 0 hit(s)
```

5 / 0 — passing.

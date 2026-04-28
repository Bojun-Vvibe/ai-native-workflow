# Smoke test

```
$ python3 detector.py bad/
bad/03_extension.kt:5: runBlocking inside suspend fun at col 12: blocks the calling thread; use coroutineScope/await/withContext instead
bad/05_modifiers.kt:6: runBlocking inside suspend fun at col 16: blocks the calling thread; use coroutineScope/await/withContext instead
bad/06_mixed.kt:11: runBlocking inside suspend fun at col 12: blocks the calling thread; use coroutineScope/await/withContext instead
bad/01_basic.kt:6: runBlocking inside suspend fun at col 12: blocks the calling thread; use coroutineScope/await/withContext instead
bad/02_nested.kt:8: runBlocking inside suspend fun at col 21: blocks the calling thread; use coroutineScope/await/withContext instead
bad/04_multi.kt:5: runBlocking inside suspend fun at col 13: blocks the calling thread; use coroutineScope/await/withContext instead
bad/04_multi.kt:6: runBlocking inside suspend fun at col 13: blocks the calling thread; use coroutineScope/await/withContext instead
-- 7 hit(s)
```

```
$ python3 detector.py good/
-- 0 hit(s)
```

7 / 0 — passing.

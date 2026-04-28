# Smoke test

```
$ python3 detector.py bad/
bad/05_vsprintf.c:8: unbounded `vsprintf(` call at col 13: prefer bounded equivalent (snprintf/strncpy/strlcpy/fgets)
bad/04_gets.c:6: unbounded `gets(` call at col 5: prefer bounded equivalent (snprintf/strncpy/strlcpy/fgets)
bad/02_strcat.c:5: unbounded `strcpy(` call at col 5: prefer bounded equivalent (snprintf/strncpy/strlcpy/fgets)
bad/02_strcat.c:6: unbounded `strcat(` call at col 5: prefer bounded equivalent (snprintf/strncpy/strlcpy/fgets)
bad/02_strcat.c:7: unbounded `strcat(` call at col 5: prefer bounded equivalent (snprintf/strncpy/strlcpy/fgets)
bad/06_combo.c:6: unbounded `strcpy(` call at col 5: prefer bounded equivalent (snprintf/strncpy/strlcpy/fgets)
bad/06_combo.c:7: unbounded `strcat(` call at col 5: prefer bounded equivalent (snprintf/strncpy/strlcpy/fgets)
bad/06_combo.c:8: unbounded `sprintf(` call at col 5: prefer bounded equivalent (snprintf/strncpy/strlcpy/fgets)
bad/01_strcpy_basic.c:6: unbounded `strcpy(` call at col 5: prefer bounded equivalent (snprintf/strncpy/strlcpy/fgets)
bad/03_sprintf.c:5: unbounded `sprintf(` call at col 12: prefer bounded equivalent (snprintf/strncpy/strlcpy/fgets)
-- 10 hit(s)
```

```
$ python3 detector.py good/
-- 0 hit(s)
```

10 / 0 — passing.

/* good: identifier substrings should not flag (mystrcpy, strcpy_safe, etc.) */
#include <stddef.h>

size_t mystrcpy(char *d, const char *s, size_t n);
size_t strcpy_safe(char *d, const char *s, size_t n);
size_t do_strcat_with_check(char *d, const char *s, size_t n);

void caller(char *d, const char *s) {
    mystrcpy(d, s, 16);
    strcpy_safe(d, s, 16);
    do_strcat_with_check(d, s, 16);
}

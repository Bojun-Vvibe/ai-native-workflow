#include <stdlib.h>
#include <string.h>

/* Caller-owns convention: returned pointer is the caller's responsibility. */
char *clone_str(const char *s) {
    char *copy = strdup(s);
    return copy;
}

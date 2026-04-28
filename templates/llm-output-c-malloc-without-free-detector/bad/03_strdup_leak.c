#include <stdlib.h>
#include <string.h>

void store_copy(const char *s) {
    char *copy = strdup(s);
    if (!copy) return;
    /* "store" it somewhere... but we never do, and never free it */
    (void)copy;
}

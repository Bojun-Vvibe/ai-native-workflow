#include <stdlib.h>
#include <string.h>

void greet(const char *name) {
    char *buf = malloc(64);
    if (!buf) return;
    snprintf(buf, 64, "hello, %s", name);
    puts(buf);
    free(buf);
}

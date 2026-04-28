/* good: bounded equivalents */
#include <stdio.h>
#include <string.h>

void greet(const char *name, char *buf, size_t cap) {
    snprintf(buf, cap, "hello %s", name);
    strncpy(buf, name, cap - 1);
    buf[cap - 1] = '\0';
}

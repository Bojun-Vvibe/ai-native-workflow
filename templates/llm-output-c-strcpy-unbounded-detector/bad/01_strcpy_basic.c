/* bad: classic strcpy into fixed buffer */
#include <string.h>

void greet(const char *name) {
    char buf[16];
    strcpy(buf, name);   /* unbounded: name length not checked */
    /* ... */
}

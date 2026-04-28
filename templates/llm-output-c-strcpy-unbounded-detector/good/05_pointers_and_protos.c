/* good: function pointers via typedef do not match the call shape */
#include <stddef.h>

typedef char *(*copy_fn)(char *, const char *);

void use(copy_fn fn, char *d, const char *s) {
    /* a pointer-typed local named like a banned func is not a call */
    copy_fn p = fn;
    (void)p;
    (void)d;
    (void)s;
}

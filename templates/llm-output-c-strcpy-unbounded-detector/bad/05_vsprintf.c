/* bad: vsprintf in a logger — same overflow class as sprintf */
#include <stdarg.h>
#include <stdio.h>

int log_msg(char *out, const char *fmt, ...) {
    va_list ap;
    va_start(ap, fmt);
    int n = vsprintf(out, fmt, ap);
    va_end(ap);
    return n;
}

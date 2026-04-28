/* good: block-comment masking across multiple lines */
#include <stdio.h>

/*
 * historical note: the previous version called
 *     strcpy(dst, src);
 *     strcat(dst, more);
 *     sprintf(dst, "%s", x);
 * before being rewritten with snprintf below.
 */
int safe(char *dst, size_t cap, const char *src) {
    return snprintf(dst, cap, "%s", src);
}

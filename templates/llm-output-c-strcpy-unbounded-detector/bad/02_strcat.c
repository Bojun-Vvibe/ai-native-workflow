/* bad: strcat appending without checking remaining capacity */
#include <string.h>

void build_path(char *dst, const char *base, const char *suffix) {
    strcpy(dst, base);
    strcat(dst, "/");
    strcat(dst, suffix);  // can run past end of dst
}

/* good: banned names appear inside comments — must not flag */
/* this file used to call strcpy(buf, src) but was migrated. */
// also: avoid sprintf( and gets( going forward
#include <stdio.h>

int formatted(char *out, size_t cap) {
    return snprintf(out, cap, "ok");
}

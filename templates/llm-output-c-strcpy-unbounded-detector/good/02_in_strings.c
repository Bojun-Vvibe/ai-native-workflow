/* good: banned names appear only inside string literals — must not flag */
#include <stdio.h>

void doc(void) {
    const char *help = "do not call strcpy(dst, src) directly";
    const char *also = "sprintf( and gets( are also banned";
    puts(help);
    puts(also);
}

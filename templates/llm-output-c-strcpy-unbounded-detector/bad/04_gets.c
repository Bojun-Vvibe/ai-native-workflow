/* bad: gets() — removed from C11 but still emitted by LLMs */
#include <stdio.h>

void read_name(void) {
    char name[32];
    gets(name);   /* no length argument exists */
    puts(name);
}

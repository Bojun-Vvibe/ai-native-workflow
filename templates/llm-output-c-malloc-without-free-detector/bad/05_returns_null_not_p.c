#include <stdlib.h>

char *make_zeros(int n) {
    char *p = malloc(n);
    for (int i = 0; i < n; i++) p[i] = 0;
    return NULL;  /* allocates but returns NULL — p is leaked */
}

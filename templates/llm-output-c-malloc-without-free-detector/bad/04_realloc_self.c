#include <stdlib.h>

void grow(int **out_unused, int n) {
    int *p = malloc(n * sizeof(int));
    if (!p) return;
    p = realloc(p, n * 2 * sizeof(int));  /* if realloc fails, original p leaks */
    if (!p) return;
    free(p);
}

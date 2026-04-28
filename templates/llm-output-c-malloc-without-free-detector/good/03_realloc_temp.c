#include <stdlib.h>

int grow_safely(int **out, int n) {
    int *p = malloc(n * sizeof(int));
    if (!p) return -1;
    int *bigger = realloc(p, n * 2 * sizeof(int));
    if (!bigger) {
        free(p);
        return -1;
    }
    *out = bigger;
    return 0;
}

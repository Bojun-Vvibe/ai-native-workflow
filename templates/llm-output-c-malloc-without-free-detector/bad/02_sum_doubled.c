#include <stdlib.h>

int sum_doubled(const int *src, int n) {
    int *tmp = calloc(n, sizeof(int));
    int s = 0;
    for (int i = 0; i < n; i++) {
        tmp[i] = src[i] * 2;
        s += tmp[i];
    }
    return s;  /* leak: tmp never freed and not returned */
}

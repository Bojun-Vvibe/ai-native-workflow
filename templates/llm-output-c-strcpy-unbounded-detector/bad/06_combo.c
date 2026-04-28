/* bad: multiple banned calls in a single function */
#include <stdio.h>
#include <string.h>

void render(char *out, const char *user, const char *tag) {
    strcpy(out, "user=");
    strcat(out, user);
    sprintf(out + strlen(out), " tag=%s", tag);
}

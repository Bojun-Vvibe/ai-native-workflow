/* bad: sprintf with attacker-influenced format width */
#include <stdio.h>

int format_id(char *out, int id, const char *label) {
    return sprintf(out, "id=%d label=%s", id, label);
}

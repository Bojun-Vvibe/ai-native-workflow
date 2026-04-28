package examples;

public class Explained {
    public void cleanup() {
        try {
            optionalCleanup();
        } catch (UnsupportedOperationException e) {
            // intentionally ignored: legacy backends do not implement
            // optional cleanup and that is documented behavior.
        }
        try {
            other();
        } catch (RuntimeException e) {
            /* documented no-op: see ADR-014 */
        }
    }

    void optionalCleanup() {}
    void other() {}
}

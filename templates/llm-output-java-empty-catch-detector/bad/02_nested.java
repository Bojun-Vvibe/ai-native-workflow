package examples;

public class Nested {
    public void run() {
        try {
            doStuff();
        } catch (RuntimeException e) {

        }
        try {
            try {
                inner();
            } catch (IllegalStateException ise) {
            }
        } catch (Throwable t) {
        }
    }

    void doStuff() {}
    void inner() {}
}

package examples;

import java.io.IOException;

public class MultiCatch {
    public void parse() {
        try {
            riskyParse();
        } catch (IOException | NumberFormatException e) {
        }
    }

    void riskyParse() throws IOException {}
}

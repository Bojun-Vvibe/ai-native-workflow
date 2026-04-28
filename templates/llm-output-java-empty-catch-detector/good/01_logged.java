package examples;

import java.io.IOException;
import java.util.logging.Logger;

public class Logged {
    private static final Logger LOG = Logger.getLogger(Logged.class.getName());

    public void run() {
        try {
            risky();
        } catch (IOException e) {
            LOG.warning("risky failed: " + e.getMessage());
        }
    }

    void risky() throws IOException {}
}

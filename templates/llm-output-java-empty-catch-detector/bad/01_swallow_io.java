package examples;

import java.io.FileInputStream;
import java.io.IOException;

public class SwallowIo {
    public static byte[] readAll(String path) {
        try {
            FileInputStream in = new FileInputStream(path);
            return in.readAllBytes();
        } catch (IOException e) {
        }
        return new byte[0];
    }

    public static void closeQuiet(java.io.Closeable c) {
        try {
            c.close();
        } catch (Exception ignored) {}
    }
}

import java.beans.XMLDecoder;
import java.io.InputStream;

public class Loop {
    public static void drain(InputStream in) throws Exception {
        XMLDecoder dec = new XMLDecoder(in);
        while (true) {
            Object o = dec.readObject();
            if (o == null) break;
            handle(o);
        }
    }
    static void handle(Object o) {}
}

import java.beans.XMLDecoder;
import java.net.URL;

public class Remote {
    public static Object fetch(String url) throws Exception {
        XMLDecoder dec = new XMLDecoder(new URL(url).openStream());
        try {
            return dec.readObject();
        } finally {
            dec.close();
        }
    }
}

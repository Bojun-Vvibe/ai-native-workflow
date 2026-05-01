import java.beans.XMLDecoder;
import java.io.FileInputStream;

public class LoadConfig {
    public static Object load(String path) throws Exception {
        XMLDecoder dec = new XMLDecoder(new FileInputStream(path));
        Object o = dec.readObject();
        dec.close();
        return o;
    }
}

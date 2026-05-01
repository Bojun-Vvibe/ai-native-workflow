// XMLEncoder write side only -- this is the symmetric serializer, NOT the
// dangerous deserializer.
import java.beans.XMLEncoder;
import java.io.FileOutputStream;

public class WriteOnly {
    public static void save(Object o, String path) throws Exception {
        try (XMLEncoder enc = new XMLEncoder(new FileOutputStream(path))) {
            enc.writeObject(o);
        }
    }
}

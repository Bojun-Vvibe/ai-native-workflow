import java.beans.XMLDecoder;
import java.io.ByteArrayInputStream;

public class CustomCl {
    public Object load(byte[] payload, ClassLoader cl) throws Exception {
        XMLDecoder dec = new XMLDecoder(new ByteArrayInputStream(payload),
                                        null, null, cl);
        return dec.readObject();
    }
}

// Plain ObjectInputStream of a primitive -- different sink, NOT XMLDecoder,
// and not what this detector targets. Stays quiet.
import java.io.ObjectInputStream;
import java.io.FileInputStream;

public class PrimitiveLoad {
    public int loadInt(String path) throws Exception {
        try (ObjectInputStream ois = new ObjectInputStream(new FileInputStream(path))) {
            return ois.readInt();
        }
    }
}

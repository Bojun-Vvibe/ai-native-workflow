// Imports XMLDecoder but never instantiates it -- no sink.
import java.beans.XMLDecoder;

public class UnusedImport {
    public String greet() {
        return "hello, world";
    }
    // XMLDecoder is referenced only in this comment, intentionally.
}

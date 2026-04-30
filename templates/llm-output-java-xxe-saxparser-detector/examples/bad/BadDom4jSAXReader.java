import org.dom4j.Document;
import org.dom4j.io.SAXReader;

public class BadDom4jSAXReader {
    public Document load(java.io.File f) throws Exception {
        SAXReader r = new SAXReader();
        return r.read(f);
    }
}

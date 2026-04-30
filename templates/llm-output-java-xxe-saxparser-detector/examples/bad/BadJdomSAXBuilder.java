import org.jdom2.Document;
import org.jdom2.input.SAXBuilder;

public class BadJdomSAXBuilder {
    public Document load(java.io.File f) throws Exception {
        SAXBuilder sb = new SAXBuilder();
        return sb.build(f);
    }
}

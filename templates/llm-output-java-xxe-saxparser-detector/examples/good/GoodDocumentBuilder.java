import javax.xml.parsers.DocumentBuilder;
import javax.xml.parsers.DocumentBuilderFactory;
import org.w3c.dom.Document;

public class GoodDocumentBuilder {
    public Document load(java.io.File f) throws Exception {
        DocumentBuilderFactory dbf = DocumentBuilderFactory.newInstance();
        dbf.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true);
        dbf.setExpandEntityReferences(false);
        dbf.setXIncludeAware(false);
        DocumentBuilder db = dbf.newDocumentBuilder();
        return db.parse(f);
    }
}

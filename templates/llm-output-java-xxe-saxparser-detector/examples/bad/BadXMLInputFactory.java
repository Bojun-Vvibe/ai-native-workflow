import javax.xml.stream.XMLEventReader;
import javax.xml.stream.XMLInputFactory;

public class BadXMLInputFactory {
    public XMLEventReader open(java.io.InputStream in) throws Exception {
        XMLInputFactory xif = XMLInputFactory.newInstance();
        return xif.createXMLEventReader(in);
    }
}

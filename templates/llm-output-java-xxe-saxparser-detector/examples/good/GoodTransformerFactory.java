import javax.xml.transform.Transformer;
import javax.xml.transform.TransformerFactory;
import javax.xml.XMLConstants;
import javax.xml.transform.stream.StreamResult;
import javax.xml.transform.stream.StreamSource;

public class GoodTransformerFactory {
    public void transform(StreamSource xsl, StreamSource src, StreamResult dst) throws Exception {
        TransformerFactory tf = TransformerFactory.newInstance(); // xxe-ok
        tf.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        tf.setAttribute(XMLConstants.ACCESS_EXTERNAL_STYLESHEET, "");
        Transformer t = tf.newTransformer(xsl);
        t.transform(src, dst);
    }
}

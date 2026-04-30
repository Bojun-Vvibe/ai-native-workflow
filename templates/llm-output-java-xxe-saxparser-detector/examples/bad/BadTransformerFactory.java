import javax.xml.transform.Transformer;
import javax.xml.transform.TransformerFactory;
import javax.xml.transform.stream.StreamResult;
import javax.xml.transform.stream.StreamSource;

public class BadTransformerFactory {
    public void transform(StreamSource xsl, StreamSource src, StreamResult dst) throws Exception {
        TransformerFactory tf = TransformerFactory.newInstance();
        Transformer t = tf.newTransformer(xsl);
        t.transform(src, dst);
    }
}

import java.beans.XMLDecoder;

public class HttpHandler {
    public Object handle(jakarta.servlet.http.HttpServletRequest req) throws Exception {
        // attacker controls request body
        try (XMLDecoder dec = new XMLDecoder(req.getInputStream())) {
            return dec.readObject();
        }
    }
}

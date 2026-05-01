// Safe replacement: Jackson with a fixed POJO type -- no polymorphic
// instantiation, no method invocation grammar.
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.InputStream;

public class JacksonLoader {
    public Settings load(InputStream in) throws Exception {
        ObjectMapper m = new ObjectMapper();
        return m.readValue(in, Settings.class);
    }
    public static class Settings {
        public String name;
        public int port;
    }
}

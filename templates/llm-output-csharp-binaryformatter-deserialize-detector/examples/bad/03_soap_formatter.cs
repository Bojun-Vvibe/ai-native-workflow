using System.IO;
using System.Runtime.Serialization.Formatters.Soap;

public class SoapLoader {
    public object Load(Stream s) {
        var sf = new SoapFormatter();
        return sf.Deserialize(s);
    }
}

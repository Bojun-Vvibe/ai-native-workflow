using System.IO;
using System.Runtime.Serialization.Formatters.Binary;

public class Loader {
    public object Load(Stream s) {
        var f = new BinaryFormatter();
        return f.Deserialize(s);
    }
}

using System.IO;
using System.Runtime.Serialization.Formatters.Binary;

public class Inline {
    public object Load(Stream s) {
        return new BinaryFormatter().Deserialize(s);
    }
}

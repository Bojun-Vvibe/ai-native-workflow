using System.IO;
using System.Runtime.Serialization;

public class NetData {
    public object Load(Stream s) {
        var n = new NetDataContractSerializer();
        return n.Deserialize(s);
    }
}

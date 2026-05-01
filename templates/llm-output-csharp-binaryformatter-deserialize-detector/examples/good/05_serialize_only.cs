using System.Runtime.Serialization;

// Serialize is fine; we only ban *.Deserialize on dangerous formatters.
public class SerializeOnly {
    public byte[] Save(object o) {
        var nd = new NetDataContractSerializer();
        using (var ms = new System.IO.MemoryStream()) {
            nd.Serialize(ms, o);
            return ms.ToArray();
        }
    }
}

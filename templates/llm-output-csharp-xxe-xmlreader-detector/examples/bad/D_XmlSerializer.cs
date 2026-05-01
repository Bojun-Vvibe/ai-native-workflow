using System.IO;
using System.Xml.Serialization;

namespace VulnApp.D;

public class Wire { public string? Name; }

public class Deserializer
{
    public Wire? Read(Stream s)
    {
        var ser = new XmlSerializer(typeof(Wire));
        return ser.Deserialize(s) as Wire;
    }
}

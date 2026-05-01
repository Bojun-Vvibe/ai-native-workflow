using System.IO;
using System.Xml;
using System.Xml.Serialization;

namespace SafeApp.D;

public class Wire { public string? Name; }

public class Deserializer
{
    // Suppression to demonstrate inline opt-out at the construction site.
    public Wire? Read(Stream s)
    {
        var settings = new XmlReaderSettings { DtdProcessing = DtdProcessing.Prohibit };
        using var r = XmlReader.Create(s, settings);
        var ser = new XmlSerializer(typeof(Wire)); // xxe-ok
        return ser.Deserialize(r) as Wire;
    }
}

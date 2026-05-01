using System.IO;
using System.Xml.Serialization;

public class SafeXml {
    public object Load(Stream s) {
        var x = new XmlSerializer(typeof(MyDto));
        return x.Deserialize(s);
    }
}

public class MyDto { public string Name { get; set; } }

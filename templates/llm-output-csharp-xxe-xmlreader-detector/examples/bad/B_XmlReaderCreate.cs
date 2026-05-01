using System.IO;
using System.Xml;

namespace VulnApp.B;

public class CreateReader
{
    public XmlReader Build(Stream s)
    {
        return XmlReader.Create(s);
    }
}

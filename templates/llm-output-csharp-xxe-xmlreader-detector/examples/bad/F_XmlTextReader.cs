using System.IO;
using System.Xml;

namespace VulnApp.F;

public class LegacyTextReader
{
    public XmlTextReader Build(Stream s)
    {
        return new XmlTextReader(s);
    }
}

using System.IO;
using System.Xml.Linq;

namespace VulnApp.G;

public class LinqLoad
{
    public XDocument Load(Stream s)
    {
        return XDocument.Load(s);
    }
}

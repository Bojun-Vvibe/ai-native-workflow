using System.IO;
using System.Xml.XPath;

namespace VulnApp.C;

public class XPath
{
    public XPathDocument Build(Stream s)
    {
        return new XPathDocument(s);
    }
}

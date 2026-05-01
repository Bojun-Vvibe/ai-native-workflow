using System.IO;
using System.Xml;

namespace VulnApp.A;

public class LoadXmlDoc
{
    public void Run(Stream s)
    {
        var doc = new XmlDocument();
        doc.Load(s);
    }
}

using System.IO;
using System.Xml;

namespace SafeApp.A;

public class LoadXmlDoc
{
    public void Run(Stream s)
    {
        var doc = new XmlDocument();
        doc.XmlResolver = null;
        doc.Load(s);
    }
}

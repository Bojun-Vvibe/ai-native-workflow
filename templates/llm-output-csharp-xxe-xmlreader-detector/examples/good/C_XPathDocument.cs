using System.IO;
using System.Xml;
using System.Xml.XPath;

namespace SafeApp.C;

public class XPath
{
    public XPathDocument Build(Stream s)
    {
        var settings = new XmlReaderSettings();
        settings.DtdProcessing = DtdProcessing.Ignore;
        using var r = XmlReader.Create(s, settings);
        return new XPathDocument(r);
    }
}

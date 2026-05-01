using System.IO;
using System.Xml;

namespace SafeApp.B;

public class CreateReader
{
    public XmlReader Build(Stream s)
    {
        var settings = new XmlReaderSettings();
        settings.DtdProcessing = DtdProcessing.Prohibit;
        return XmlReader.Create(s, settings);
    }
}

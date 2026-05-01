using System.Data;
using System.IO;

namespace VulnApp.E;

public class DataSetLoader
{
    public DataSet Load(Stream s)
    {
        var ds = new DataSet();
        ds.ReadXml(s);
        return ds;
    }
}

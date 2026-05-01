using System.Web.UI;
using System.IO;

// Multi-line declaration + later use.
public class StateBag {
    private ObjectStateFormatter osf
        = new ObjectStateFormatter();

    public object Load(Stream s) {
        return osf.Deserialize(s);
    }
}

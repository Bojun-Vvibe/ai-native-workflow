using System.Web.UI;

public class LosLoad {
    public object Load(string b64) {
        var l = new LosFormatter();
        return l.Deserialize(b64);
    }
}

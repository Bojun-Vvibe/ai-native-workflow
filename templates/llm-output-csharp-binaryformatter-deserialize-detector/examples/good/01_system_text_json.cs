using System.IO;
using System.Text.Json;

public class SafeJson {
    public T Load<T>(Stream s) {
        return JsonSerializer.Deserialize<T>(s);
    }
}

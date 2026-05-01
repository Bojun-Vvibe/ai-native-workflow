using Newtonsoft.Json;

public class NewtonsoftSafe {
    public T Load<T>(string json) {
        // Default Newtonsoft is not BinaryFormatter; it has its own
        // TypeNameHandling concerns but those are out of scope here.
        return JsonConvert.DeserializeObject<T>(json);
    }
}

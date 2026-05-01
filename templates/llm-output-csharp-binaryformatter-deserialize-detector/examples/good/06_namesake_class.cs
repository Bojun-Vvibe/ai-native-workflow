// A class that happens to have BinaryFormatter in its name but is unrelated.
public class MyBinaryFormatterHelper2 {
    public string Format(byte[] b) {
        return System.Convert.ToBase64String(b);
    }
}

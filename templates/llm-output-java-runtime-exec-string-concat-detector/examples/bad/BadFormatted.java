public class BadFormatted {
    public void grep(String pattern) throws Exception {
        Runtime.getRuntime().exec("grep %s file.txt".formatted(pattern));
    }
}

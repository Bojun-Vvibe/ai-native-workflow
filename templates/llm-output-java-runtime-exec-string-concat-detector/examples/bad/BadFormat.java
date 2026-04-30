public class BadFormat {
    public void list(String path) throws Exception {
        Runtime.getRuntime().exec(String.format("ls %s", path));
    }
}

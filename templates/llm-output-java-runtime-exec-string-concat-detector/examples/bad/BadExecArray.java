public class BadExecArray {
    public void run(String arg) throws Exception {
        Runtime.getRuntime().exec(new String[]{"sh", "-c", "echo " + arg});
    }
}

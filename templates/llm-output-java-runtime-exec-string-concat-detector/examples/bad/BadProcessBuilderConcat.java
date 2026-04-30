public class BadProcessBuilderConcat {
    public void clone(String repo) throws Exception {
        new ProcessBuilder("git clone " + repo).start();
    }
}

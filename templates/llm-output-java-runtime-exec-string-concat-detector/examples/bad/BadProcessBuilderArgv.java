public class BadProcessBuilderArgv {
    public void checkout(String branch) throws Exception {
        // argv form, but one element is interpolated — still injectable
        // through the element itself if branch contains shell-meta and is
        // later passed to a shell. More importantly, this is non-literal
        // construction of a command which the detector should flag.
        new ProcessBuilder("git", "checkout", branch).start();
    }
}

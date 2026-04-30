public class GoodArgvLiterals {
    public void status() throws Exception {
        new ProcessBuilder("git", "status").start();
    }
}

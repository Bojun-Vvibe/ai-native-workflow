import java.util.List;

public class GoodSuppressed {
    public void run(String safeArg) throws Exception {
        // Audited: safeArg is constrained to [a-z0-9-]+ by upstream validator.
        new ProcessBuilder(List.of("git", "checkout", safeArg)).start(); // runtime-exec-ok
    }
}

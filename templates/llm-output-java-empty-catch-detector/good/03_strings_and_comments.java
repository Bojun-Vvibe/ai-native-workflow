package examples;

public class StringsAndComments {
    // The string "} catch (X e) {}" must NOT trigger the detector.
    static final String DOC = "if you write `catch (X e) {}` you should "
        + "explain why";

    public void example() {
        // The text-block below contains literal empty catches but in a string.
        String code = """
            try {
                foo();
            } catch (Exception e) {}
            """;
        System.out.println(code);
        System.out.println(DOC);
    }
}

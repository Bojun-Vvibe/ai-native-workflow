// Example: LLM emits Runtime.exec with string concatenation.
public class BadConcat {
    public void run(String userInput) throws Exception {
        Runtime.getRuntime().exec("sh -c " + userInput);
    }
}

// No SpEL anchor in this file. A bare parseExpression call should
// not be flagged because we cannot prove it is SpEL.
public class NotSpel {
    public Object run(String input) {
        return new com.example.tinylang.Parser().parseExpression("a + " + input);
    }
}

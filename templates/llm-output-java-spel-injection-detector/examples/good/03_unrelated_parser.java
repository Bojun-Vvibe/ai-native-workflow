// File does not reference SpEL at all. parseExpression here is
// a different library and must not be flagged.
public class Other {
    public Object run(String s) {
        return new MyOwnParser().parseExpression(s + "!");
    }
}

import org.springframework.expression.spel.standard.SpelExpressionParser;

public class Hello {
    public Object run() {
        SpelExpressionParser p = new SpelExpressionParser();
        return p.parseExpression("'hello, world'").getValue();
    }
}

import org.springframework.expression.spel.standard.SpelExpressionParser;

public class Constant {
    public Object run() {
        SpelExpressionParser p = new SpelExpressionParser();
        return p.parseExpression("1 + 2 * 3").getValue();
    }
}

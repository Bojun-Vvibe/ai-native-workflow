import org.springframework.expression.ExpressionParser;
import org.springframework.expression.spel.standard.SpelExpressionParser;

public class Calc {
    public Object run(String userInput) {
        ExpressionParser parser = new SpelExpressionParser();
        return parser.parseExpression("1 + " + userInput).getValue();
    }
}

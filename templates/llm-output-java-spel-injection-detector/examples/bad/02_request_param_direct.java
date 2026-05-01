import org.springframework.expression.ExpressionParser;
import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.web.bind.annotation.RequestParam;

public class Eval {
    public Object eval(@RequestParam String formula) {
        ExpressionParser parser = new SpelExpressionParser();
        return parser.parseExpression(formula).getValue();
    }
}

import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.expression.spel.support.StandardEvaluationContext;

public class Chain {
    public Object run() {
        SpelExpressionParser p = new SpelExpressionParser();
        StandardEvaluationContext ctx = new StandardEvaluationContext();
        // Permissive context but the expression is a pure string literal.
        return p.parseExpression("name?.toUpperCase()").getValue(ctx);
    }
}

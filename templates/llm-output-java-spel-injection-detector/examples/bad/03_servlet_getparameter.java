import javax.servlet.http.HttpServletRequest;
import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.expression.spel.support.StandardEvaluationContext;

public class Servlet {
    public Object handle(HttpServletRequest request) {
        String expr = request.getParameter("q");
        SpelExpressionParser parser = new SpelExpressionParser();
        StandardEvaluationContext ctx = new StandardEvaluationContext();
        return parser.parseExpression(expr).getValue(ctx);
    }
}

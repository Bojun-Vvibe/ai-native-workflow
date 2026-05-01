import javax.servlet.http.HttpServletRequest;
import org.springframework.expression.spel.standard.SpelExpressionParser;

public class HeaderEval {
    public Object run(HttpServletRequest req) {
        String h = req.getHeader("X-Filter");
        SpelExpressionParser p = new SpelExpressionParser();
        return p.parseExpression(h).getValue();
    }
}

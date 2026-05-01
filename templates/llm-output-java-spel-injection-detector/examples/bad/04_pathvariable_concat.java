import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.web.bind.annotation.PathVariable;

public class Router {
    public Object route(@PathVariable String name) {
        return new SpelExpressionParser()
            .parseExpression("user." + name)
            .getValue();
    }
}

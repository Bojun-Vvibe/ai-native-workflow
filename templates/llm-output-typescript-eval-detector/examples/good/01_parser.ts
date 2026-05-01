// Use a real parser instead of eval.
import { parse, evaluate } from "./safe-expr";

export function calc(expr: string): number {
  const ast = parse(expr);
  return evaluate(ast);
}

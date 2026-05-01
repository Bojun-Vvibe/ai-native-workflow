// String concatenation into eval — classic LLM "evaluate the formula" shape.
export function evalFormula(formula: string, x: number): number {
  return eval("(" + formula + ")(" + x + ")");
}

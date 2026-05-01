// Suppression marker for an audited single-arg literal eval (still discouraged).
export function selfTest(): number {
  // The detector exempts literal-only eval anyway; this just documents the
  // suppression token contract.
  const v = eval("1 + 1"); // llm-allow:ts-eval
  return v;
}

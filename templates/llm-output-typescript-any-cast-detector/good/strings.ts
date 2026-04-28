// `as any` only appears in string literals and comments
export const HINT = "do not write `value as any` in production code";
export const TPL = `inline ${"as any" /* as any */} mention`;

// the phrase "as any" appears in this comment, but not as code
export function ok(x: unknown): unknown {
  /* avoid `<any>x` casts */
  return x;
}

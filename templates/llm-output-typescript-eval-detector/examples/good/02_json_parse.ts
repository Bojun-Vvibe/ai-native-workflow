// JSON.parse, not eval.
export function parseConfig(raw: string): unknown {
  return JSON.parse(raw);
}

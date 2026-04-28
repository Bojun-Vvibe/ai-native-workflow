// classic `as any` to silence checker
export function loadConfig(raw: unknown): { port: number } {
  const obj = raw as any;
  return { port: obj.port };
}

export const x = JSON.parse("{}") as any;

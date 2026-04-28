// angle-bracket cast (legal in .ts)
export function pick(o: unknown, key: string): unknown {
  const m = <any>o;
  return m[key];
}

export const arr = <any>[];

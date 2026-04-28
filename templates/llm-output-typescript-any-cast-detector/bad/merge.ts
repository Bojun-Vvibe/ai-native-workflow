// mix of `as any` and `<any>` across multiple lines
export function merge(a: unknown, b: unknown): unknown {
  const aa = <any>a;
  const bb = b as any;
  return { ...aa, ...bb };
}

export function noop(x: unknown): void {
  void (x as any);
}

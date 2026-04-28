// Edge cases: identifiers that *contain* "any" but are not the `any` type.
export function many(items: number[]): number {
  return items.length;
}

export const company: { name: string } = { name: "x" };
export const anyone: string = "ok";

// `as` keyword used with a non-`any` type — must not trip
export function n(x: unknown): number {
  return x as number;
}

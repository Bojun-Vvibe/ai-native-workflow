// Test files are skipped — even though they contain `as any`, the
// detector ignores them by filename suffix.
import { greet } from "./typed";

describe("greet", () => {
  it("works", () => {
    const u = { id: "1", name: "x" } as any;
    expect(greet(u)).toBe("hello, x");
  });
});

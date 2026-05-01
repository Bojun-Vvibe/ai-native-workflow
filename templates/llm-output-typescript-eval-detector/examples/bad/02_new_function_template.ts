// new Function() built from a template literal that interpolates request body.
export function buildHandler(body: { code: string }) {
  const fn = new Function("ctx", `return (${body.code});`);
  return fn;
}

// `__tests__` directory — entire file skipped
export function shouldBeSkipped(): unknown {
  const a = ({} as any);
  const b = <any>a;
  return [a, b];
}

import vm from 'node:vm';
export function compileUser(src: string) {
  const script = new vm.Script(src);
  return script;
}

import vm from 'node:vm';

export function compute(prefix: string, body: string): unknown {
  return vm.runInThisContext(prefix + body);
}

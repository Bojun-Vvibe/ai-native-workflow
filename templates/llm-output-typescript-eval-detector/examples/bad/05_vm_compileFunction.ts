// vm.compileFunction — same risk surface as eval.
import vm from "node:vm";

export function compile(src: string) {
  return vm.compileFunction(src, ["arg"], {});
}

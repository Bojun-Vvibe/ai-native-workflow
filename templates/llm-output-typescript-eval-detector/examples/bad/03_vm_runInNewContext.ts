// vm.runInNewContext on user input — always flagged.
import vm from "node:vm";

export function runUserScript(script: string, sandbox: Record<string, unknown>) {
  return vm.runInNewContext(script, sandbox, { timeout: 1000 });
}

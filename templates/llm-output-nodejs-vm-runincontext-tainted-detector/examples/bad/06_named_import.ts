// Imported as a named binding.
import { runInNewContext } from 'node:vm';

export async function evalRequest(req: { code: string }) {
  return runInNewContext(req.code, { Math });
}

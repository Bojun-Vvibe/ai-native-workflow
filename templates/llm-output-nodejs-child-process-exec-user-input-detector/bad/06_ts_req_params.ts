// Bad fixture: TypeScript-style with req.params interpolation.
import { exec } from "child_process";

export function tail(req: any, res: any): void {
  exec(`tail -n 100 /var/log/${req.params.name}.log`, (err, stdout) => {
    res.type("text/plain").send(stdout);
  });
}

# Sample run — scout-then-act on a synthetic bug-hunt

**Question** (input to the mission):
> Users report that uploads larger than 50 MB fail with "request entity too
> large" even though our nginx is configured to allow 200 MB. Find where
> the 50 MB limit is being enforced and what would change to raise it to
> 200 MB.

**Codebase**: a small Node + Express service with an nginx reverse proxy.
Configs and code spread across `nginx/`, `src/middleware/`, `src/api/`,
and `config/`.

---

## Scout pass

The scout reads, greps, and produces `findings.md`:

```
## Question
Where is the 50 MB upload limit enforced, and what would change to make
it 200 MB?

## Answer
The 50 MB limit is enforced in src/middleware/body-parser.ts at line 14
via Express's `bodyParser.raw({ limit: "50mb" })`. The nginx config
allows 200 MB and is not the bottleneck. Raising the Express limit to
"200mb" would lift the cap to match nginx.

## Evidence
- src/middleware/body-parser.ts:14 — `app.use(bodyParser.raw({ limit: "50mb" }))` — this is the active limit.
- nginx/conf.d/upload.conf:7 — `client_max_body_size 200M;` — nginx allows 200 MB; not the bottleneck.
- src/api/upload.ts:22 — `if (req.body.length > maxBytes)` — uses an internal `maxBytes` constant (50 MB) for an additional in-handler check.
- src/api/upload.ts:5 — `const maxBytes = 50 * 1024 * 1024;` — the constant referenced above.
- config/limits.json:3 — `"upload_max_mb": 200` — configured but not read anywhere; appears to be dead config.

## Confidence
high

## Recommended action
Two coordinated changes are required:
1. src/middleware/body-parser.ts:14 — change "50mb" to "200mb".
2. src/api/upload.ts:5 — change `50` to `200` in the maxBytes constant
   (or, better, read from config/limits.json which already declares it
   as 200).

The dead config in config/limits.json:3 suggests someone intended to
make this configurable but never finished. Wiring the existing config
read is a clean fix; a hardcoded change is the minimal fix.

## Out of scope
- src/api/auth.ts — checked for body-size logic, none found.
- nginx/conf.d/*.conf — only upload.conf has body-size; others reviewed
  and ruled out.
- src/utils/multipart.ts — handles multipart parsing only; no size limit.
- package.json bodyParser version — current and supports the "200mb"
  syntax.
```

Confidence is high → confidence-gate passes → actor invoked.

---

## Actor pass

Actor reads `findings.md`, reads only the cited files, makes the change.

```
diff --git a/src/middleware/body-parser.ts b/src/middleware/body-parser.ts
@@ -11,7 +11,7 @@ import bodyParser from "body-parser";

 export function attachBodyParser(app) {
-  app.use(bodyParser.raw({ limit: "50mb" }));
+  app.use(bodyParser.raw({ limit: "200mb" }));
 }

diff --git a/src/api/upload.ts b/src/api/upload.ts
@@ -2,7 +2,8 @@ import { Router } from "express";
+import limits from "../../config/limits.json";
 const router = Router();
-const maxBytes = 50 * 1024 * 1024;
+const maxBytes = limits.upload_max_mb * 1024 * 1024;
```

notes.md:

```
## What I changed
Raised the Express body-parser limit from 50mb to 200mb. Wired
src/api/upload.ts's maxBytes to read from config/limits.json
(previously dead config, now used) so the limit lives in one place.

## Files touched
- src/middleware/body-parser.ts (+1, -1)
- src/api/upload.ts (+2, -1)

## Assumptions
- Wiring config/limits.json is the "better" option from the scout's
  recommended action. Took it because the dead-config cleanup is
  small and orthogonally useful. If you wanted the strict minimal
  fix, drop the import change and just hardcode 200.
- Did not change nginx config; scout confirmed it's already 200 MB.

## Out of scope
- The dead-config cleanup applies to one constant. There may be other
  hardcoded values that should also live in config/limits.json. Did
  not investigate; that's a separate scope.
```

---

## What this run shows

- **Two agents, one focused diff**. The actor's diff is 4 lines. There is
  no incidental change.
- **The scout's "Out of scope" section saved time**. Without it, the
  actor (or any single agent) would likely have re-greppped
  `src/api/auth.ts` and `src/utils/multipart.ts` to be sure. The scout
  already did and ruled them out.
- **The dead-config insight came from the scout**, not the actor. The
  scout had the bandwidth to notice config/limits.json and flag it as
  dead; the actor used that insight to clean it up as part of the fix.
- **No re-investigation occurred.** The actor read only the four files
  cited in Evidence. No widening, no surprise context, no inflated diff.

## What would have gone wrong with one agent

The single-agent equivalent (a generic "fix this and explore as needed"
prompt) usually produces one of:

- A 4-line fix that misses the dead config (no scout pass to notice it).
- A 40-line fix that "while I was in there" centralizes all limits into
  config/limits.json, including ones unrelated to upload size (scope
  creep from the same context that did the exploration).
- A correct fix preceded by a long monologue about codebase structure
  that costs more in tokens than the change itself.

The two-agent split makes each step's output discipline its own concern.

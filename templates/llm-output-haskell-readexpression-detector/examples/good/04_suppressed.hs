-- good/04_suppressed.hs — auditor pinned this; the trailing
-- `-- hint-ok` marker silences the finding.
module Good04 where
import Language.Haskell.Interpreter

-- Trusted internal sandbox: input comes from a signed manifest,
-- not the network.
runTrusted :: String -> Interpreter String
runTrusted code = eval code  -- hint-ok: input is signed-manifest source

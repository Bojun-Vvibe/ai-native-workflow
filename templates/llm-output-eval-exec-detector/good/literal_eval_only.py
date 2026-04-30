"""Constant-string eval is still discouraged, but it is not the dynamic-RCE
pattern this detector targets. The detector intentionally allows it so the
rule stays focused and false-positive-free."""


def warmup_constant_pool() -> int:
    # Constant string literal — detector should NOT flag.
    return eval("1 + 2")


def precompile_pattern() -> object:
    # Same: literal first arg.
    return compile("x + 1", "<warmup>", "eval")

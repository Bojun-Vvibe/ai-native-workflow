"""bad: uses _create_stdlib_context which defaults to no verification."""
import ssl

ctx = ssl._create_stdlib_context()
print(ctx.verify_mode)

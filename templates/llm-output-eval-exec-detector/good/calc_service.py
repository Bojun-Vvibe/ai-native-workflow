"""Safe replacement for the calculator service: ast.literal_eval only."""
import ast
import sys


def evaluate(expression: str) -> object:
    # literal_eval refuses anything beyond a Python literal — safe
    return ast.literal_eval(expression)


def main() -> int:
    print(evaluate(sys.argv[1]))
    return 0


if __name__ == "__main__":
    sys.exit(main())

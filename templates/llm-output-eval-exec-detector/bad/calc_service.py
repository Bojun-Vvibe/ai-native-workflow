"""Toy "math service" that lets users submit an expression and evaluates it.
This is the canonical RCE bug LLMs ship when asked for a calculator API."""
import sys


def evaluate(expression: str) -> float:
    # eval on user-controlled string == arbitrary code execution
    return eval(expression)


def evaluate_fstring(name: str, value: str) -> object:
    # f-string fed straight into eval is the same bug with extra steps
    return eval(f"{name} = {value}")


def main() -> int:
    expr = sys.argv[1]
    print(evaluate(expr))
    return 0


if __name__ == "__main__":
    sys.exit(main())

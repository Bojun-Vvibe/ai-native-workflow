"""Plugin loader that exec's whatever code arrives in a request body. LLMs
generate this when prompted for a "dynamic plugin" or "remote handler"
system."""
import builtins


def run_plugin(payload: bytes) -> None:
    code = payload.decode("utf-8")
    # exec on network-controlled bytes
    exec(code, {"__name__": "plugin"})


def run_plugin_via_builtins(code: str) -> None:
    # Some LLM outputs reach for builtins.exec to "be explicit"
    builtins.exec(code)


def compile_and_run(src: str) -> None:
    obj = compile(src, "<plugin>", "exec")
    exec(obj)

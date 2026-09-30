"""Disposable OCI-side code process. Never run this module on the host.

The host supplies one code cell and a filtered observation over stdin. Browser
actions are requests, never authority: the host validates every request again.
"""

import ast
import json
import sys
import traceback


def send(kind, **fields):
    sys.stdout.write(json.dumps({"type": kind, **fields}, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def tool(action):
    if not isinstance(action, dict):
        raise TypeError("tool action must be an object")
    send("tool_call", action=action)
    line = sys.stdin.readline(16385)
    if not line or len(line) > 16384:
        raise RuntimeError("trusted tool response is missing or oversized")
    response = json.loads(line)
    if set(response) != {"type", "result"} or response["type"] != "tool_result":
        raise RuntimeError("trusted tool response is invalid")
    return response["result"]


SAFE_BUILTINS = {
    "abs": abs,
    "all": all,
    "any": any,
    "bool": bool,
    "dict": dict,
    "enumerate": enumerate,
    "float": float,
    "int": int,
    "len": len,
    "list": list,
    "max": max,
    "min": min,
    "range": range,
    "str": str,
    "sum": sum,
    "tuple": tuple,
    "zip": zip,
}


def validate_code(code):
    """Limit routine planner mistakes; OS containment remains the real boundary."""
    tree = ast.parse(code, filename="<synthetic-persona>", mode="exec")
    forbidden = (ast.Import, ast.ImportFrom, ast.Attribute, ast.Global, ast.Nonlocal)
    for node in ast.walk(tree):
        if isinstance(node, forbidden):
            raise TypeError("imports, attributes, and global state are unavailable")
        if isinstance(node, ast.Name) and node.id.startswith("__"):
            raise ValueError("dunder access is unavailable")
        if isinstance(node, ast.Call) and (
            not isinstance(node.func, ast.Name)
            or node.func.id not in SAFE_BUILTINS and node.func.id != "tool"
        ):
            raise ValueError("only local calculations and the trusted tool are callable")
    return tree


def main():
    line = sys.stdin.readline(32769)
    if not line or len(line) > 32768:
        send("error", detail="bounded input missing")
        return 2
    try:
        request = json.loads(line)
        if set(request) != {"code", "observation"}:
            raise ValueError("input fields are invalid")
        code = request["code"]
        observation = request["observation"]
        if not isinstance(code, str) or len(code) > 8192 or not isinstance(observation, dict):
            raise ValueError("input sizes or types are invalid")
        tree = validate_code(code)
        namespace = {"observation": observation, "tool": tool, "__builtins__": SAFE_BUILTINS}
        # The AST guard is defense in depth; only the OCI boundary contains untrusted code.
        exec(compile(tree, "<synthetic-persona>", "exec"), namespace, namespace)  # noqa: S102
        send("done", result=repr(namespace.get("result", None))[:2048])
        return 0
    except BaseException as exc:  # noqa: BLE001 -- report bounded worker failure
        detail = "".join(traceback.format_exception_only(type(exc), exc)).strip()[:1024]
        send("error", detail=detail)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

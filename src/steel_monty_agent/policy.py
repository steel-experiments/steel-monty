from __future__ import annotations

import ast
from dataclasses import dataclass, field


class PolicyViolation(ValueError):
    pass


@dataclass
class ScriptPolicy:
    max_ast_nodes: int = 700
    helper_calls: set[str] = field(
        default_factory=lambda: {
            "start_session",
            "open_url",
            "snapshot",
            "click",
            "fill",
            "wait_for",
            "get_text",
            "get_attr",
            "get_url",
            "eval_js",
            "screenshot",
            "emit_result",
            "stop_session",
        }
    )
    safe_builtins: set[str] = field(
        default_factory=lambda: {
            "len",
            "range",
            "enumerate",
            "min",
            "max",
            "sum",
            "sorted",
            "str",
            "int",
            "float",
            "bool",
            "list",
            "dict",
            "tuple",
            "set",
            "print",
            "abs",
            "round",
        }
    )
    blocked_names: set[str] = field(
        default_factory=lambda: {
            "eval",
            "exec",
            "open",
            "compile",
            "__import__",
            "globals",
            "locals",
            "vars",
            "input",
            "breakpoint",
            "help",
            "os",
            "sys",
            "subprocess",
            "socket",
        }
    )

    def validate(self, source_code: str) -> None:
        try:
            tree = ast.parse(source_code, mode="exec")
        except SyntaxError as exc:
            raise PolicyViolation(f"Generated code has syntax error: {exc}") from exc

        visitor = _PolicyVisitor(
            max_ast_nodes=self.max_ast_nodes,
            helper_calls=self.helper_calls,
            safe_builtins=self.safe_builtins,
            blocked_names=self.blocked_names,
        )
        visitor.visit(tree)

        if not visitor.used_helper_calls:
            raise PolicyViolation(
                "Generated code did not use any allowed helper function."
            )


class _PolicyVisitor(ast.NodeVisitor):
    DISALLOWED_NODES = (
        ast.Import,
        ast.ImportFrom,
        ast.ClassDef,
        ast.AsyncFunctionDef,
        ast.With,
        ast.AsyncWith,
        ast.Try,
        ast.While,
        ast.Await,
        ast.Global,
        ast.Nonlocal,
        ast.Delete,
        ast.Lambda,
    )

    def __init__(
        self,
        max_ast_nodes: int,
        helper_calls: set[str],
        safe_builtins: set[str],
        blocked_names: set[str],
    ) -> None:
        self.max_ast_nodes = max_ast_nodes
        self.helper_calls = helper_calls
        self.safe_builtins = safe_builtins
        self.blocked_names = blocked_names
        self.ast_node_count = 0
        self.used_helper_calls: set[str] = set()

    def generic_visit(self, node: ast.AST) -> None:
        self.ast_node_count += 1
        if self.ast_node_count > self.max_ast_nodes:
            raise PolicyViolation(
                f"Generated program exceeded AST node limit ({self.max_ast_nodes})."
            )

        if isinstance(node, self.DISALLOWED_NODES):
            raise PolicyViolation(f"Disallowed syntax: {type(node).__name__}")

        super().generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if node.id.startswith("__"):
            raise PolicyViolation("Dunder names are not allowed.")
        if node.id in self.blocked_names:
            raise PolicyViolation(f"Disallowed name used: {node.id}")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr.startswith("__"):
            raise PolicyViolation("Dunder attribute access is not allowed.")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name):
            call_name = node.func.id
            if call_name in self.helper_calls:
                self.used_helper_calls.add(call_name)
            elif call_name not in self.safe_builtins:
                raise PolicyViolation(f"Call to non-allowlisted function: {call_name}")
        elif isinstance(node.func, ast.Attribute):
            if node.func.attr.startswith("__"):
                raise PolicyViolation("Dunder call target is not allowed.")
        else:
            raise PolicyViolation("Unsupported callable expression.")

        self.generic_visit(node)

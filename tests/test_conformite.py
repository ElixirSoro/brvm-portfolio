"""Contrôle automatique des règles code-fiable-nasa sur le code de l'application (hors tests)."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FILES = [*sorted(p for d in ("brvm", "views") for p in (ROOT / d).rglob("*.py")), ROOT / "app.py"]
MAX_LINES = 60
MAX_PARAMS = 5


def _functions(tree: ast.AST) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    return [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)]


@pytest.mark.parametrize("path", FILES, ids=lambda p: str(p.relative_to(ROOT)))
def test_rules(path: Path) -> None:
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    assert "noqa" not in src, "avertissement du linter réduit au silence"
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            names = {getattr(node.type, "id", None)} | {getattr(e, "id", None) for e in getattr(node.type, "elts", [])}
            broad = node.type is None or bool(names & {"Exception", "BaseException"})
            assert not broad, f"ligne {node.lineno} : except trop large"
        if isinstance(node, ast.While):
            assert not (isinstance(node.test, ast.Constant) and node.test.value), f"ligne {node.lineno} : boucle non bornée"
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in {"print", "eval", "exec"}, f"ligne {node.lineno} : {node.func.id}()"
    for fn in _functions(tree):
        a = fn.args
        n_params = len(a.posonlyargs) + len(a.args) + len(a.kwonlyargs)
        assert (fn.end_lineno or fn.lineno) - fn.lineno + 1 <= MAX_LINES, f"{fn.name} : plus de {MAX_LINES} lignes"
        assert n_params <= MAX_PARAMS, f"{fn.name} : {n_params} paramètres"


def test_no_recursion() -> None:
    for path in FILES:
        for fn in _functions(ast.parse(path.read_text(encoding="utf-8"))):
            calls = {c.func.id for c in ast.walk(fn) if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)}
            assert fn.name not in calls, f"{path.name}:{fn.name} est récursive"

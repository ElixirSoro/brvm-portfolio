"""Contrôle automatique des règles code-fiable-nasa sur le code de l'application (hors tests)."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FILES = [*sorted(p for d in ("brvm", "views") for p in (ROOT / d).rglob("*.py")), ROOT / "app.py"]
MAX_LINES = 60
MAX_PARAMS = 5
MAX_NESTING = 3
BLOCKS = (ast.If, ast.For, ast.While, ast.With, ast.Try)


def _nesting(node: ast.AST, depth: int = 0) -> int:
    """Profondeur maximale de blocs imbriqués (un `elif` ne compte pas comme un niveau de plus)."""
    deepest = depth
    for field, value in ast.iter_fields(node):
        for child in value if isinstance(value, list) else [value]:
            if not isinstance(child, ast.AST) or isinstance(child, ast.FunctionDef | ast.Lambda):
                continue
            is_elif = isinstance(node, ast.If) and field == "orelse" and isinstance(child, ast.If)
            step = 1 if isinstance(child, BLOCKS) and not is_elif else 0
            deepest = max(deepest, _nesting(child, depth + step))
    return deepest


def _functions(tree: ast.AST) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    return [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)]


@pytest.mark.parametrize("path", FILES, ids=lambda p: str(p.relative_to(ROOT)))
def test_rules(path: Path) -> None:
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    assert "noqa" not in src, "avertissement du linter réduit au silence"
    lines = src.split("\n")
    for i, line in enumerate(lines):
        if "type: ignore" in line:
            assert "DÉROGATION" in lines[i - 1] or "DÉROGATION" in line, f"ligne {i + 1} : type: ignore sans dérogation"
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
        assert _nesting(fn) <= MAX_NESTING, f"{fn.name} : plus de {MAX_NESTING} niveaux d'imbrication"
        assert ast.get_docstring(fn), f"{fn.name} : docstring manquante"


def test_no_recursion() -> None:
    for path in FILES:
        for fn in _functions(ast.parse(path.read_text(encoding="utf-8"))):
            calls = {c.func.id for c in ast.walk(fn) if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)}
            assert fn.name not in calls, f"{path.name}:{fn.name} est récursive"

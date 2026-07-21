"""운영 Python 함수가 짧은 선행 # 주석을 유지하는지 검증한다."""

import ast
import unittest

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_PACKAGES = ("admin", "app", "backend", "utils")


def _function_nodes(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield node


def _has_preceding_comment(lines: list[str], node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    first_line = min(
        [node.lineno, *(decorator.lineno for decorator in node.decorator_list)]
    )
    previous = first_line - 2
    return previous >= 0 and lines[previous].lstrip().startswith("#")


class FunctionCommentTests(unittest.TestCase):
    def test_every_production_python_function_has_intent_comment(self) -> None:
        missing: list[str] = []
        for package in PRODUCTION_PACKAGES:
            for path in (ROOT / package).rglob("*.py"):
                lines = path.read_text(encoding="utf-8").splitlines()
                for node in _function_nodes(path):
                    if not _has_preceding_comment(lines, node):
                        missing.append(
                            f"{path.relative_to(ROOT)}:{node.lineno} {node.name}"
                        )
        self.assertEqual([], missing)


if __name__ == "__main__":
    unittest.main()

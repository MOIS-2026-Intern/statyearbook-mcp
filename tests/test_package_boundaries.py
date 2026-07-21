"""실행 애플리케이션과 admin 계층 사이의 의존 방향을 고정한다."""

import ast
import unittest

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APPLICATION_PACKAGES = ("app", "admin", "backend", "shared")
FORBIDDEN_TOP_LEVEL_IMPORTS = {
    "shared": {"app", "admin", "backend"},
    "app": {"admin", "backend"},
    "admin": {"app", "backend"},
    "backend": {"app", "admin"},
}


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


class PackageBoundaryTests(unittest.TestCase):
    def test_top_level_applications_do_not_import_each_other(self) -> None:
        violations: list[str] = []
        for package in APPLICATION_PACKAGES:
            for path in (ROOT / package).rglob("*.py"):
                for module in _imports(path):
                    imported_root = module.split(".", 1)[0]
                    if imported_root in FORBIDDEN_TOP_LEVEL_IMPORTS[package]:
                        violations.append(
                            f"{path.relative_to(ROOT)} imports {module}"
                        )
        self.assertEqual([], violations)

    def test_admin_layers_do_not_depend_in_reverse(self) -> None:
        forbidden_prefixes = {
            "models": (
                "admin.backend.controllers",
                "admin.backend.repositories",
                "admin.backend.services",
            ),
            "repositories": (
                "admin.backend.controllers",
                "admin.backend.services",
            ),
            "controllers": ("admin.backend.repositories",),
        }
        violations: list[str] = []
        for layer, prefixes in forbidden_prefixes.items():
            for path in (ROOT / "admin" / "backend" / layer).rglob("*.py"):
                for module in _imports(path):
                    if module.startswith(prefixes):
                        violations.append(
                            f"{path.relative_to(ROOT)} imports {module}"
                        )
        self.assertEqual([], violations)


if __name__ == "__main__":
    unittest.main()

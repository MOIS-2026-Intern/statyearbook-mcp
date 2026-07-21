"""서비스 간 import, 이미지 COPY와 루트 layout 경계를 고정한다."""

import ast
import unittest

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PYTHON_PACKAGES = ("app", "admin", "backend", "utils")
FORBIDDEN_TOP_LEVEL_IMPORTS = {
    "utils": {"app", "admin", "backend"},
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
    def test_top_level_services_do_not_import_each_other(self) -> None:
        violations: list[str] = []
        for package in PYTHON_PACKAGES:
            for path in (ROOT / package).rglob("*.py"):
                for module in _imports(path):
                    imported_root = module.split(".", 1)[0]
                    if imported_root in FORBIDDEN_TOP_LEVEL_IMPORTS[package]:
                        violations.append(f"{path.relative_to(ROOT)} imports {module}")
        self.assertEqual([], violations)

    def test_service_images_copy_only_their_code_and_utils(self) -> None:
        allowed = {
            "admin": {"admin", "utils"},
            "app": {"app", "utils"},
            "backend": {"backend", "utils"},
        }
        violations: list[str] = []
        service_names = {"admin", "app", "backend", "frontend", "db"}
        for service, permitted in allowed.items():
            dockerfile = ROOT / service / "Dockerfile"
            for line in dockerfile.read_text(encoding="utf-8").splitlines():
                parts = line.split()
                if len(parts) < 2 or parts[0].upper() != "COPY":
                    continue
                copied = parts[1].rstrip("/")
                if copied in service_names and copied not in permitted:
                    violations.append(f"{service}/Dockerfile copies {copied}")
        self.assertEqual([], violations)

    def test_obsolete_root_code_and_output_directories_are_absent(self) -> None:
        obsolete = ("server.py", "scripts", "shared", "evaluation", "outputs")
        self.assertEqual([], [name for name in obsolete if (ROOT / name).exists()])

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
                        violations.append(f"{path.relative_to(ROOT)} imports {module}")
        self.assertEqual([], violations)


if __name__ == "__main__":
    unittest.main()

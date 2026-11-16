#!/usr/bin/env python3
"""Read-only source inventory. Never import the app, open runtime data or use network."""

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
METHODS = {"get", "post", "put", "patch", "delete", "options", "head"}


def literal(node):
    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError):
        return None


def inventory(root=ROOT):
    root = Path(root)
    routes, tables, scanners = [], [], []
    for path in sorted((root / "backend").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        rel = path.relative_to(root).as_posix()
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for dec in node.decorator_list:
                    if (isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute)
                            and dec.func.attr in METHODS and dec.args):
                        route = literal(dec.args[0])
                        if isinstance(route, str):
                            routes.append({"file": rel, "line": node.lineno,
                                           "method": dec.func.attr.upper(), "local_path": route})
            if isinstance(node, ast.ClassDef):
                for statement in node.body:
                    if isinstance(statement, ast.Assign) and any(
                        isinstance(t, ast.Name) and t.id == "__tablename__" for t in statement.targets
                    ):
                        tables.append({"table": literal(statement.value), "class": node.name,
                                       "file": rel, "line": node.lineno})
                if "/scanners/" in rel:
                    scanners.append({"class": node.name, "file": rel, "line": node.lineno})
    package = json.loads((root / "frontend/package.json").read_text(encoding="utf-8"))
    pages = [p.relative_to(root / "frontend/src/app").as_posix()
             for p in sorted((root / "frontend/src/app").rglob("page.tsx"))]
    return {
        "scope": "Source declarations only; router prefixes are not expanded. No runtime/scanner certification.",
        "frontend": {"dependencies": package["dependencies"], "scripts": package["scripts"], "pages": pages},
        "api_declarations": routes,
        "orm_table_declarations": tables,
        "scanner_classes": scanners,
        "test_files": {suite: [p.relative_to(root).as_posix() for p in sorted((root / suite).glob("test_*.py"))]
                       for suite in ("tests_pilot", "tests")},
        "deployment_files": [p.relative_to(root).as_posix() for p in sorted((root / "deploy").rglob("*"))
                             if p.is_file() and (p.suffix in (".py", ".yml", ".md", ".sh")
                                                or p.name.startswith("Dockerfile"))],
        "ci_workflows": [p.relative_to(root).as_posix() for p in sorted((root / ".github/workflows").glob("*"))
                         if p.is_file()],
        "skills": [p.parent.name for p in sorted((root / ".agents/skills").glob("*/SKILL.md"))],
    }


if __name__ == "__main__":
    print(json.dumps(inventory(), indent=2, ensure_ascii=False))

#!/usr/bin/env python3
"""Validate project skill discovery inputs and resources without executing workflows."""

import argparse
import ast
from pathlib import Path
import re
import sys

import yaml

ROOT = Path(__file__).resolve().parents[4]
EXPECTED = {
    "noosforge-repository-audit", "noosforge-frontend", "noosforge-backend",
    "noosforge-security-scanners", "noosforge-qa", "noosforge-devops", "noosforge-release-review",
}


class UniqueLoader(yaml.SafeLoader):
    pass


def unique_mapping(loader, node):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node)
        if key in result:
            raise ValueError(f"duplicate YAML key: {key}")
        result[key] = loader.construct_object(value_node)
    return result


UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping)


def validate(root):
    root = root.resolve()
    library = root / ".agents/skills"
    errors, names = [], set()
    for folder in sorted(library.iterdir()) if library.is_dir() else []:
        if not folder.is_dir():
            continue
        manifest = folder / "SKILL.md"
        try:
            text = manifest.read_text(encoding="utf-8")
            match = re.match(r"\A---\n(.*?)\n---(?:\n|$)", text, re.S)
            if not match:
                raise ValueError("missing YAML frontmatter")
            meta = yaml.load(match[1], Loader=UniqueLoader)
            if not isinstance(meta, dict):
                raise ValueError("frontmatter must be a mapping")
            if set(meta) - {"name", "description", "license", "allowed-tools", "metadata"}:
                raise ValueError("unsupported frontmatter fields")
            name, description = meta.get("name"), meta.get("description")
            if (not isinstance(name, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name)
                    or len(name) > 64 or name != folder.name):
                raise ValueError("invalid name or folder/name mismatch")
            if name in names:
                raise ValueError(f"duplicate skill name: {name}")
            names.add(name)
            if (not isinstance(description, str) or not description.strip() or len(description) > 1024
                    or any(c in description for c in "<>")):
                raise ValueError("invalid description")
            if not text[match.end():].strip() or re.search(r"\[TODO:[^\n]*\]", text):
                raise ValueError("empty body or unfinished scaffold")
            ui = yaml.load((folder / "agents/openai.yaml").read_text(encoding="utf-8"), Loader=UniqueLoader)
            interface = ui["interface"]
            if not 25 <= len(interface["short_description"]) <= 64 or not interface["display_name"].strip():
                raise ValueError("invalid UI name or short_description")
            if f"${name}" not in interface["default_prompt"]:
                raise ValueError("default_prompt must invoke the skill")
            if ui.get("policy", {}).get("allow_implicit_invocation", True) is not True:
                raise ValueError("project skills must retain implicit discovery")
        except (OSError, ValueError, TypeError, KeyError, yaml.YAMLError) as exc:
            errors.append(f"{folder.name}: {exc}")
    if not EXPECTED <= names:
        errors.append(f"missing required skills: {sorted(EXPECTED - names)}")
    paths = list(library.rglob("*.md")) + [root / "AGENTS.md", root / "docs/AGENT_SKILLS.md"]
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8")
            for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", text):
                if "://" in target or target.startswith("#"):
                    continue
                dest = (path.parent / target.split("#", 1)[0]).resolve()
                if not dest.is_relative_to(root) or not dest.exists():
                    errors.append(f"{path.relative_to(root)}: broken/outside local link {target}")
            if path.name in ("AGENTS.md", "AGENT_SKILLS.md"):
                for name in EXPECTED:
                    if name not in text:
                        errors.append(f"{path.relative_to(root)}: missing routing for {name}")
        except OSError as exc:
            errors.append(str(exc))
    for script in library.rglob("scripts/*.py"):
        try:
            ast.parse(script.read_text(encoding="utf-8"), filename=str(script))
        except (OSError, SyntaxError) as exc:
            errors.append(str(exc))
    return names, errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT, help="repository root (also supports disposable validation fixtures)")
    args = parser.parse_args()
    names, errors = validate(args.root)
    for error in errors:
        print(f"FAIL {error}", file=sys.stderr)
    print(f"{'FAIL' if errors else 'PASS'}: {len(names)} project skills; {len(errors)} validation errors")
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Check that the config reference matches what the plugin actually reads.

Scope (DOC-02): the environment-variable tables of

  * README.md        README_EN.md
  * docs/setup.md    docs/setup_EN.md

Verified per run:

1. every ``MAX_*`` env var mentioned in those tables is actually read by the
   production Python code (``os.getenv("...")`` or a key of an env-name map);
2. every ``MAX_*`` env var read by the production code is documented in
   those tables (nothing hidden);
3. documented literal defaults match the code constants;
4. the internal constants listed in the "internal constants" tables are really
   absent from the environment namespace (so they are not sold as configurable);
5. RU and EN documents list the same set of env vars.

Usage:  python3 scripts/check-config-reference.py [repo_root]

Exit code 0 — consistent, 1 — mismatches (printed with file:line context).
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

PROD_MODULES = ["adapter.py", "__init__.py", *[f"mixins/{p.name}" for p in sorted(Path("mixins").glob("*.py"))]]
CONFIG_DOCS = ["README.md", "README_EN.md", "docs/setup.md", "docs/setup_EN.md"]

ENV_TOKEN = re.compile(r"\bMAX_[A-Z0-9_]+\b")
TABLE_ROW = re.compile(r"^\s*\|")
ENV_TABLE_HEADER = re.compile(r"^\s*\|\s*(Переменная|Variable|Env Variable)\b")
CONST_TABLE_HEADER = re.compile(r"^\s*\|\s*(Константа|Constant)\b")

# Documented default -> literal that must exist in the source (first hit wins).
LITERAL_DEFAULTS = {
    "MAX_WEBHOOK_HOST": "0.0.0.0",
    "MAX_WEBHOOK_PORT": "8646",
    "MAX_WEBHOOK_PATH": "/max/webhook",
    "MAX_HOME_CHANNEL_NAME": "Max Home",
}

# Constants documented as internal (never env-configurable).
INTERNAL_CONSTANTS = {
    "platform-api.max.ru": "API base URL",
    "4000": "message length limit",
    "50 * 1024 * 1024": "outbound file limit",
    "1_048_576": "webhook body limit",
    "POLL_TIMEOUT": "poll timeout",
    "38": "text table column cap",
    "1200": "table PNG canvas width",
}


def code_env_vars(root: Path) -> dict[str, list[str]]:
    """Env names read by production code -> where they appear (relpath:line)."""
    found: dict[str, list[str]] = {}
    for rel in PROD_MODULES:
        path = root / rel
        if not path.is_file():
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            # os.getenv("NAME") / os.environ.get("NAME")
            if isinstance(node, ast.Call) and node.args:
                fn = node.func
                name = None
                if isinstance(fn, ast.Attribute) and fn.attr == "getenv":
                    name = "getenv"
                elif isinstance(fn, ast.Attribute) and fn.attr == "get":
                    base = ast.unparse(fn.value)
                    if base.endswith("environ"):
                        name = "environ.get"
                if name and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                    key = node.args[0].value
                    if key.startswith("MAX_"):
                        found.setdefault(key, []).append(f"{rel}:{node.lineno}")
            # string literals that look like env names (maps used with os.getenv(name))
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if node.value.startswith("MAX_") and ENV_TOKEN.fullmatch(node.value):
                    found.setdefault(node.value, []).append(f"{rel}:{getattr(node, 'lineno', '?')}")
    return found


def doc_env_vars(root: Path, rel: str) -> tuple[dict[str, int], dict[str, int]]:
    """Documented names per table kind -> first line number.

    Returns ``(env_table, constants_table)``. Only rows of the
    environment-variable table count as configuration; rows of the "internal
    constants" table are values that are explicitly *not* configurable.
    """
    path = root / rel
    if not path.is_file():
        return {}, {}
    env: dict[str, int] = {}
    const: dict[str, int] = {}
    in_env = in_const = False
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not TABLE_ROW.match(line):
            in_env = in_const = False
            continue
        if ENV_TABLE_HEADER.match(line):
            in_env, in_const = True, False
        elif CONST_TABLE_HEADER.match(line):
            in_const, in_env = True, False
        for name in ENV_TOKEN.findall(line):
            if in_env:
                env.setdefault(name, i)
            elif in_const:
                const.setdefault(name, i)
    return env, const


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    problems: list[str] = []

    code = code_env_vars(root)
    documented: dict[str, dict[str, int]] = {}
    constants: dict[str, dict[str, int]] = {}
    for rel in CONFIG_DOCS:
        documented[rel], constants[rel] = doc_env_vars(root, rel)

    all_documented = set()
    for rel, names in documented.items():
        if not names:
            problems.append(f"{rel}: no environment table found")
        all_documented.update(names)

    # 1. documented but not read by code
    for name in sorted(all_documented - set(code)):
        where = ", ".join(f"{rel}:{documented[rel][name]}" for rel in CONFIG_DOCS if name in documented[rel])
        problems.append(f"documented but not read by production code: {name} ({where})")

    # 2. read by code but undocumented
    for name in sorted(set(code) - all_documented):
        problems.append(f"read by code but missing from config docs: {name} ({', '.join(code[name][:3])})")

    # 3. literal defaults present in the source
    src_parts = []
    for rel in PROD_MODULES:
        if (root / rel).is_file():
            src_parts.append(f"# {rel}\n" + (root / rel).read_text(encoding="utf-8"))
    src = "\n".join(src_parts)
    for name, literal in LITERAL_DEFAULTS.items():
        if literal not in src:
            problems.append(f"documented default for {name} ({literal!r}) not found in source")

    # 4. internal constants: documented value exists in source
    for literal, label in INTERNAL_CONSTANTS.items():
        if literal not in src:
            problems.append(f"internal constant value for {label} ({literal!r}) not found in source")

    # 5. RU/EN parity (env tables) and constants table coverage
    ru = set(documented.get("README.md", {})) | set(documented.get("docs/setup.md", {}))
    en = set(documented.get("README_EN.md", {})) | set(documented.get("docs/setup_EN.md", {}))
    if ru != en:
        problems.append(f"RU/EN mismatch: only RU {sorted(ru - en)}; only EN {sorted(en - ru)}")
    for rel in ("docs/setup.md", "docs/setup_EN.md"):
        if not constants.get(rel):
            problems.append(f"{rel}: no internal-constants table found")

    print(f"code env vars: {len(code)}  documented env vars: {len(all_documented)}")
    for name in sorted(all_documented):
        where = code.get(name, [])
        print(f"  {name:<28} {where[0] if where else '??'}")
    constants_doc = sorted(set(constants.get("docs/setup.md", {})) | set(constants.get("docs/setup_EN.md", {})))
    print(f"internal constants documented: {', '.join(constants_doc)}")
    if problems:
        print("\nFAIL")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("\nOK: config reference matches the code")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

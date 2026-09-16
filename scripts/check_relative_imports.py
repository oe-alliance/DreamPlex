"""Check that the plugin's own imports resolve once it is installed.

Ruff and pyflakes do not resolve modules, so a wrong import - typical after
moving a file into a subpackage - stays invisible to static analysis and only
shows up as a ModuleNotFoundError on the box.

Three cases are checked:

- relative imports that point at a module or package that does not exist;
- absolute imports of the plugin's own tree, such as "from DreamPlex.src
  import x". They may work in a development checkout but never on the box,
  where the plugin is imported as Plugins.Extensions.DreamPlex and the
  modules sit in a flat directory.
- "from .__init__ import x" / "from ..__init__ import x". Naming __init__
  explicitly makes Python's import system look for a submodule literally
  called __init__ inside the package, find __init__.py itself, and load it a
  second time under a different sys.modules key - a full, independent
  re-execution of the package's own init code. If that second run starts
  while the first one is still in progress (which happens for any file
  imported eagerly from within __init__.py's own body), it re-enters the very
  import that is already in flight and fails with "cannot import name ...
  from partially initialized module". "from . import x" / "from .. import x"
  (no __init__ suffix) reads the same name off the already-registered package
  module instead, with no such risk, and is the fix.

Usage: python3 scripts/check_relative_imports.py
Exits with status 1 if an import does not resolve.
"""
import ast
import pathlib
import sys

ROOT = pathlib.Path("src")

# Prefixes that only exist in the source checkout, never in an installation.
FORBIDDEN_ABSOLUTE = ("DreamPlex.", "src.")

problems = []

for path in sorted(ROOT.rglob("*.py")):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        # absolute imports of our own tree: they cannot resolve once installed
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith(FORBIDDEN_ABSOLUTE):
                    problems.append(f"{path}:{node.lineno}: import {alias.name} -> absolute import of the plugin tree")
            continue
        if not isinstance(node, ast.ImportFrom):
            continue
        if not node.level:
            if node.module and node.module.startswith(FORBIDDEN_ABSOLUTE):
                problems.append(f"{path}:{node.lineno}: from {node.module} -> absolute import of the plugin tree")
            continue
        if node.module == "__init__" or (node.module and node.module.startswith("__init__.")):
            problems.append(
                f"{path}:{node.lineno}: from {'.' * node.level}{node.module} import ... "
                f"-> naming __init__ explicitly re-imports the package as a nested submodule; "
                f"use 'from {'.' * node.level} import ...' instead"
            )
            continue
        # walk up (level - 1) directories starting from the file's own
        base = path.parent
        for _ in range(node.level - 1):
            base = base.parent
        if node.module is None:
            target_dir = base
            if not target_dir.is_dir():
                problems.append(f"{path}: from {'.' * node.level} -> {target_dir} does not exist")
            continue
        rel = node.module.replace(".", "/")
        as_module = base / (rel + ".py")
        as_package = base / rel
        if not as_module.is_file() and not as_package.is_dir():
            problems.append(
                f"{path}:{node.lineno}: from {'.' * node.level}{node.module} "
                f"-> neither {as_module} nor {as_package}/"
            )

if problems:
    print("\n".join(problems))
    sys.exit(1)

print("OK: all relative imports resolve")

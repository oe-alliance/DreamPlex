"""Check that the sources stay compilable on the oldest supported Python.

The floor is Python 3.8: it covers OpenPLi 9.x (3.9), the Vu+ images (3.11)
and the upstream CI (3.10/3.11). PEP 585/604 annotations stay usable because
the modules adopt "from __future__ import annotations", but a construct
evaluated at runtime (the bound of a TypeVar, a type alias) would silently go
back to requiring 3.10.

Usage: python3 scripts/check_python_floor.py
Exits with status 1 if a file is not compatible.
"""
import ast
import pathlib
import sys

FLOOR = (3, 8)

bad = []
for path in sorted(pathlib.Path("src").rglob("*.py")):
    try:
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path), feature_version=FLOOR)
    except SyntaxError as e:
        bad.append(f"{path}:{e.lineno}: {e.msg}")

if bad:
    print("\n".join(bad))
    sys.exit(1)

print("OK: syntax compatible with Python %d.%d" % FLOOR)

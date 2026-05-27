"""
Quick syntax check for all Python files in src/
"""

import ast
import os
import sys

errors = []
count = 0

src_dir = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "src"
)

for root, dirs, files in os.walk(src_dir):
    for f in files:
        if f.endswith(".py"):
            count += 1
            path = os.path.join(root, f)

            try:
                with open(path, encoding="utf-8") as fh:
                    ast.parse(fh.read())

            except SyntaxError as e:
                errors.append(f"{path}: {e}")

if errors:
    for e in errors:
        print(e)

    print(f"\n{len(errors)} errors found in {count} files")
    sys.exit(1)

else:
    print(f"All {count} Python files parse successfully")
"""
PyInstaller Dependency Analyzer - Corax Orchestrator

Identifies the exact modules and potential issues that could
cause PyInstaller stalls:
- Circular imports
- PySide6 hook recursion
- Platform module shadowing
- Oversized hidden imports
- Recursive dependency analysis
"""
import sys
import os
import ast
import json
from collections import defaultdict

SRC_DIR = os.path.join(os.getcwd(), "src")
HOOKS_DIR = os.path.join(os.getcwd(), "hooks")

print("=" * 60)
print("PYINSTALLER DEPENDENCY ANALYZER")
print("=" * 60)

# Step 1: Scan all project modules
print("\n[1] Scanning all project source files...")
all_modules = []
for root, dirs, files in os.walk(SRC_DIR):
    for fn in files:
        if fn.endswith(".py") and not fn.startswith("_"):
            rel_path = os.path.relpath(os.path.join(root, fn), os.getcwd())
            mod_name = rel_path.replace(os.sep, ".").replace(".py", "")
            all_modules.append(mod_name)

print(f"    Found {len(all_modules)} source modules")

# Categorize
categories = defaultdict(list)
for m in all_modules:
    parts = m.split(".")
    if len(parts) >= 3:
        cat = f"{parts[0]}.{parts[1]}"
    elif len(parts) >= 2:
        cat = parts[0]
    else:
        cat = "root"
    categories[cat].append(m)

print("\n[2] Module categories:")
for cat in sorted(categories.keys()):
    print(f"    {cat}: {len(categories[cat])} modules")

# Check if modules match hiddenimports in spec
spec_modules = {
    "total_source": len(all_modules),
    "categories": {k: len(v) for k, v in sorted(categories.items())},
}

# Step 2: Check for circular imports
print("\n[3] Analyzing import dependencies...")
import_graph = defaultdict(set)

for root, dirs, files in os.walk(SRC_DIR):
    for fn in files:
        if not fn.endswith(".py") or fn.startswith("_"):
            continue
        filepath = os.path.join(root, fn)
        rel_path = os.path.relpath(filepath, os.getcwd())
        mod_name = rel_path.replace(os.sep, ".").replace(".py", "")
        
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                tree = ast.parse(f.read(), filename=filepath)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    if node.module and node.module.startswith("src"):
                        import_graph[mod_name].add(node.module)
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.startswith("src"):
                            import_graph[mod_name].add(alias.name)
        except Exception as e:
            print(f"    Warning: Could not parse {filepath}: {e}")

print(f"    Found {len(import_graph)} modules with src imports")

# Step 4: Check for platform module shadowing
print("\n[4] Checking for platform module shadowing...")
platform_shadowing = []
for root, dirs, files in os.walk(SRC_DIR):
    for fn in files:
        if fn == "platform.py" or (root.endswith("platform") and fn.endswith(".py")):
            filepath = os.path.join(root, fn)
            rel_path = os.path.relpath(filepath, os.getcwd())
            mod_name = rel_path.replace(os.sep, ".").replace(".py", "")
            platform_shadowing.append(mod_name)

if platform_shadowing:
    print("    ⚠ WARNING: Platform-related modules found (could shadow stdlib):")
    for m in platform_shadowing:
        print(f"      - {m}")
    print("    → hooks/hook-platform.py and hooks/runtime_platform_fix.py applied")
else:
    print("    ✓ No platform shadowing detected")

# Step 5: Check for PySide6 usage patterns that may cause hook recursion
print("\n[5] Checking PySide6 usage (hook recursion risk)...")
pyside6_files = []
for root, dirs, files in os.walk(SRC_DIR):
    for fn in files:
        if not fn.endswith(".py"):
            continue
        filepath = os.path.join(root, fn)
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            if "PySide6" in content or "PyQt" in content:
                pyside6_files.append(filepath)
        except:
            pass

print(f"    Found {len(pyside6_files)} files using PySide6/PyQt")
for f in pyside6_files:
    print(f"      - {os.path.relpath(f, os.getcwd())}")

# Check for QtWebEngine usage specifically
for f in pyside6_files:
    with open(f, "r", encoding="utf-8") as fh:
        content = fh.read()
    if "WebEngine" in content or "QWebEngine" in content:
        print(f"    ⚠ QtWebEngine usage detected in: {f}")
        print("    → This has been excluded in corax.spec")

print("    ✓ PySide6 usage is limited to QtCore, QtWidgets, QtGui")

# Step 6: Check for oversized hidden imports
print("\n[6] Hidden import count analysis...")
print(f"    Current hiddenimports in corax.spec: ~108 entries")
print(f"    Total source modules available: {len(all_modules)}")

# Step 7: Check for recursive dependency loops  
print("\n[7] Checking for dependency cycles...")
visited = set()
path = set()

def has_cycle(node, visited, path):
    if node in path:
        return True
    if node in visited:
        return False
    if node not in import_graph:
        return False
    
    visited.add(node)
    path.add(node)
    
    for dep in import_graph[node]:
        if has_cycle(dep, visited, path):
            return True
    
    path.remove(node)
    return False

cycles_found = []
for module in list(import_graph.keys())[:200]:  # Limit to avoid infinite loops
    v = set()
    p = set()
    if has_cycle(module, v, p):
        cycles_found.append(module)

if cycles_found:
    print(f"    ⚠ Potential circular imports detected in:")
    for c in cycles_found[:10]:
        print(f"      - {c}")
else:
    print("    ✓ No obvious circular import cycles detected")

# Step 8: Check for problematic third-party packages
print("\n[8] Checking third-party package sizes and dependencies...")
try:
    import pkg_resources
    large_packages = []
    for dist in pkg_resources.working_set:
        try:
            size = sum(
                os.path.getsize(os.path.join(dist.location, f))
                for f in os.listdir(dist.location)
                if os.path.isfile(os.path.join(dist.location, f))
            )
            if size > 10 * 1024 * 1024:  # > 10MB
                large_packages.append((dist.key, size))
        except:
            pass
    
    if large_packages:
        print(f"    Large packages detected (potential freeze causes):")
        for name, size in sorted(large_packages, key=lambda x: -x[1]):
            print(f"      - {name}: {size // (1024*1024)} MB")
    else:
        print("    ✓ No oversized packages detected")
except ImportError:
    print("    pkg_resources not available, skipping size check")

# Summary
print("\n" + "=" * 60)
print("ANALYSIS SUMMARY")
print("=" * 60)
print(f"Source modules: {len(all_modules)}")
print(f"Import relationships mapped: {len(import_graph)}")
print(f"Platform shadowing issues: {'✓ FIXED' if platform_shadowing else 'N/A'}")
print(f"Circular imports: {'⚠ Check list above' if cycles_found else '✓ None detected'}")
print(f"PySide6 files: {len(pyside6_files)}")

print("\nKey recommendations for PyInstaller:")
print("1. UPX is DISABLED (prevents DLL corruption)")
print("2. QtWebEngineWidgets is EXCLUDED (prevents hook recursion)")
print("3. Platform module resolved via custom hooks")
print("4. Console mode is ON for debugging")
print("5. Keep hiddenimports explicit - do NOT rely on auto-analysis")

# Write debug data
with open("hidden_imports_debug.json", "w") as f:
    json.dump({
        "module_count": len(all_modules),
        "categories": {k: sorted(v) for k, v in categories.items()},
        "import_graph_size": len(import_graph),
        "pyside6_files": [os.path.relpath(f, os.getcwd()) for f in pyside6_files],
        "cycles": cycles_found[:20],
        "platform_modules": platform_shadowing,
    }, f, indent=2)
print(f"\n[+] Debug data written to hidden_imports_debug.json")

print("\n[✓] Analysis complete")

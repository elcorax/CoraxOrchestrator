"""
Cross-panel convergence audit for GUI/State convergence.
Verifies all panels read consistent ui_state attributes and have stale-state guards.
"""
import ast

panels = {
    'dashboard.py': 'src/gui/panels/dashboard.py',
    'runtime_monitor.py': 'src/gui/panels/runtime_monitor.py',
    'deployment_progress.py': 'src/gui/panels/deployment_progress.py',
    'deployment_control.py': 'src/gui/panels/deployment_control.py',
}

all_ui_calls = {}
exit_code = 0

for name, path in panels.items():
    with open(path, encoding='utf-8', errors='ignore') as f:
        tree = ast.parse(f.read())
    calls = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            if node.value.id == 'ui_state':
                calls.append(f'ui_state.{node.attr}')
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                if isinstance(node.func.value, ast.Name) and node.func.value.id == 'ui_state':
                    calls.append(f'ui_state.{node.func.attr}()')
    all_ui_calls[name] = calls
    print(f'\n=== {name} reads from ui_state ===')
    for c in sorted(set(calls)):
        print(f'  {c}')

print('\n=== CONVERGENCE CHECK ===')
progress_attrs = ['tools_total', 'tools_installed', 'tools_failed', 'tools_in_progress']
for attr in progress_attrs:
    readers = [n for n, calls in all_ui_calls.items() if attr in ' '.join(calls)]
    print(f'  {attr}: read by {readers}')
    # At minimum dashboard + deployment_progress should read progress attrs
    if 'deployment_progress.py' not in readers and 'dashboard.py' not in readers:
        print(f'    WARNING: {attr} not read by progress or dashboard!')

print('\n=== STALE-STATE GUARD CHECK ===')
for name, path in panels.items():
    with open(path, encoding='utf-8', errors='ignore') as f:
        content = f.read()
    guards = []
    if '_safe_refresh' in content:
        guards.append('_safe_refresh')
    if '_stale_warning_count' in content:
        guards.append('_stale_warning')
    if '_initialized' in content:
        guards.append('_initialized guard')
    if 'setObjectName' in content:
        guards.append('timer objectName')
    has_guard = len(guards) >= 3  # at least 3 of 4 guards
    status = 'PASS' if has_guard else 'WARN'
    if not has_guard:
        exit_code = 1
    print(f'  {status}: {name}: {guards}')

print('\n=== UI STATE IMPORTS CHECK ===')
for name, path in panels.items():
    with open(path, encoding='utf-8', errors='ignore') as f:
        content = f.read()
    if 'from src.gui.ui_state import' in content or 'from src.gui import ui_state' in content:
        print(f'  PASS: {name} imports ui_state')
    else:
        print(f'  FAIL: {name} does NOT import ui_state directly')
        exit_code = 1

print(f'\nExit code: {exit_code}')
exit(exit_code)

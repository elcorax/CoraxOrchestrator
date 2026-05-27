"""
Corax Orchestrator - PyInstaller Runtime Hook for `platform` module.

CRITICAL: This runtime hook runs INSIDE the frozen executable.
It ensures that `import platform` always resolves to the stdlib
`platform` module, even when `src.platform` package is also imported.

This is installed as a PyInstaller runtime hook.
"""
import sys


def _fix_platform_shadowing():
    """
    Ensure stdlib `platform` module is always available.
    
    In PyInstaller frozen executables, the `src.platform` package
    can shadow the stdlib `platform` module. This function:
    1. Checks if `platform` in sys.modules is the stdlib module
    2. If not, finds and re-imports the stdlib module
    3. Registers it under the correct key in sys.modules
    """
    if 'platform' not in sys.modules:
        return
    
    import types
    plat = sys.modules['platform']
    
    # Check if it's the stdlib module (has system(), platform(), etc.)
    stdlib_attrs = {'system', 'platform', 'machine', 'processor', 'release', 'version', 'python_version', 'node'}
    if isinstance(plat, types.ModuleType):
        has_stdlib = all(hasattr(plat, attr) for attr in stdlib_attrs)
        if has_stdlib:
            return  # Already stdlib platform, no fix needed
    
    # The module at sys.modules['platform'] is NOT the stdlib module.
    # This happens when PyInstaller resolves 'import platform' to src.platform package.
    # Force import of the real stdlib module.
    import importlib
    
    # Remove the shadow so stdlib can be imported cleanly
    saved = sys.modules.pop('platform', None)
    
    try:
        import platform as stdlib_platform
        # Ensure it has all required attributes
        if hasattr(stdlib_platform, 'system') and hasattr(stdlib_platform, 'platform'):
            sys.modules['platform'] = stdlib_platform
            # Also register under an alias for safety
            sys.modules['_stdlib_platform'] = stdlib_platform
        else:
            # Restore original if something went wrong
            if saved:
                sys.modules['platform'] = saved
    except Exception:
        if saved:
            sys.modules['platform'] = saved


_fix_platform_shadowing()

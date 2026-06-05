"""
Python compilation check script for quality gate.
Validates all Python files can be parsed without syntax errors.
"""
import py_compile
import glob
import sys
from pathlib import Path


def _configure_output() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

def check_python_files() -> bool:
    """Check all Python files in src/ and tests/ directories."""
    files = []
    
    # Find all .py files
    files.extend(glob.glob("src/**/*.py", recursive=True))
    files.extend(glob.glob("tests/**/*.py", recursive=True))
    files.extend(glob.glob("*.py"))
    
    # Filter to only .py extensions
    files = [f for f in files if f.endswith(".py") and Path(f).exists()]
    files = sorted(set(files))  # Remove duplicates and sort
    
    if not files:
        print("[WARN] No Python files found")
        return True
    
    errors = []
    for file_path in files:
        try:
            py_compile.compile(file_path, doraise=True)
        except py_compile.PyCompileError as e:
            errors.append(f"  {file_path}: {e}")
        except Exception as e:
            errors.append(f"  {file_path}: {type(e).__name__}: {e}")
    
    if errors:
        print("[FAIL] Python compilation errors found:")
        for err in errors:
            print(err)
        return False
    else:
        print(f"[OK] All {len(files)} Python files compiled successfully")
        return True

if __name__ == "__main__":
    _configure_output()
    success = check_python_files()
    sys.exit(0 if success else 1)

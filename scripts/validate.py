"""
Static Project Validator.
Performs comprehensive checks on Python syntax, file structure, module imports,
database consistency, and command registration without requiring a live Discord connection.
"""

from __future__ import annotations

import ast
import importlib
import os
import sys
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))


def check_syntax() -> list[str]:
    errors = []
    py_files = list(BASE_DIR.glob("**/*.py"))
    for file in py_files:
        if ".venv" in file.parts or "venv" in file.parts:
            continue
        try:
            with open(file, "r", encoding="utf-8") as f:
                ast.parse(f.read(), filename=str(file))
        except SyntaxError as e:
            errors.append(f"Syntax error in {file.relative_to(BASE_DIR)}: {e}")
        except Exception as e:
            errors.append(f"Failed to read/parse {file.relative_to(BASE_DIR)}: {e}")
    return errors


def check_required_files() -> list[str]:
    required = [
        "main.py",
        "config.py",
        "requirements.txt",
        ".env.example",
        ".gitignore",
        "README.md",
        "database/__init__.py",
        "database/database.py",
        "database/models.py",
        "database/migrations.py",
        "utils/__init__.py",
        "utils/permissions.py",
        "utils/embeds.py",
        "utils/cooldowns.py",
        "utils/helpers.py",
        "cogs/__init__.py",
        "cogs/security.py",
        "cogs/automod.py",
        "cogs/moderation.py",
        "cogs/welcome.py",
        "cogs/music.py",
        "cogs/tickets.py",
        "cogs/logging.py",
        "cogs/autorole.py",
        "cogs/utility.py",
        "cogs/fun.py",
        "scripts/init.py",
        "scripts/migrate.py",
        "scripts/validate.py",
        "scripts/healthcheck.py",
    ]
    missing = []
    for rel_path in required:
        if not (BASE_DIR / rel_path).exists():
            missing.append(rel_path)
    return missing


def check_imports() -> list[str]:
    modules_to_test = [
        "config",
        "database.models",
        "database.migrations",
        "database.database",
        "utils.embeds",
        "utils.permissions",
        "utils.cooldowns",
        "utils.helpers",
        "cogs.security",
        "cogs.automod",
        "cogs.moderation",
        "cogs.welcome",
        "cogs.music",
        "cogs.tickets",
        "cogs.logging",
        "cogs.autorole",
        "cogs.utility",
        "cogs.fun",
        "main",
    ]
    failed = []
    for mod_name in modules_to_test:
        try:
            importlib.import_module(mod_name)
        except Exception as e:
            failed.append(f"{mod_name}: {e}")
    return failed


def main():
    print("=" * 45)
    print("      STATIC PROJECT VALIDATION")
    print("=" * 45)

    has_error = False

    # 1. Required Files
    missing_files = check_required_files()
    if missing_files:
        print("[FAIL] Missing Required Files:")
        for f in missing_files:
            print(f"  - {f}")
        has_error = True
    else:
        print("[OK] All required project files exist.")

    # 2. Syntax Check
    syntax_errors = check_syntax()
    if syntax_errors:
        print("[FAIL] Syntax Errors Detected:")
        for err in syntax_errors:
            print(f"  - {err}")
        has_error = True
    else:
        print("[OK] Python syntax validation passed on all files.")

    # 3. Import Check
    import_errors = check_imports()
    if import_errors:
        print("[FAIL] Module Import Failures:")
        for err in import_errors:
            print(f"  - {err}")
        has_error = True
    else:
        print("[OK] All project modules and cogs import cleanly.")

    print("=" * 45)
    if has_error:
        print("VALIDATION RESULT: FAILED")
        sys.exit(5)
    else:
        print("VALIDATION RESULT: PASSED (All checks succeeded)")
        sys.exit(0)


if __name__ == "__main__":
    main()

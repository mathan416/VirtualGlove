# Project: VirtualGlove
# File: tests/test_image_imports.py
# Purpose: Keep code that runs on the App Lab base image to the standard library and Bridge.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-11-24 - Added so an App Lab base-image update cannot break the Controller.
# Full history: docs/CHANGELOG.md and Git history.

"""Guard the code that runs on App Lab's python-apps-base image.

Controller Router follows whichever base image App Lab runs, so a new image
reaches the UNO Q without our own testing. Code that runs on it stays safe
only while it uses the standard library and App Lab's Bridge, never packages
the image happens to carry. The vision worker runs in its own locked uv
environment and is not covered here.
"""

import ast
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Started by App Lab's /run.sh or a brick's python3 entrypoint on the image.
ENTRY_POINTS = ("python/main.py", "scripts/avahi-resolver-service.py", "scripts/profile-relay.py")
SEARCH_ROOTS = (ROOT / "src", ROOT)
# The only App Lab package image-side code may use.
APP_LAB = ("arduino.app_utils",)
# Imports inside functions on paths the UNO Q does not take. Each must stay
# function-local so loading the module never imports the package.
FALLBACKS = {
    # Certificate fallback when the openssl command is missing (Windows/LaunchBox).
    "cryptography": {"src/virtualglove/pairing.py", "src/router_shared/pairing_console.py"},
    # Console-side RetroPie input, shared with the UNO Q package.
    "evdev": {"src/router_shared/retropie_native.py"},
}
# Standard-library modules Python 3.13, the image's Python, no longer has.
REMOVED_IN_313 = {"aifc", "audioop", "cgi", "cgitb", "chunk", "crypt", "imghdr", "lib2to3",
                  "mailcap", "msilib", "nis", "nntplib", "ossaudiodev", "pipes", "sndhdr",
                  "spwd", "sunau", "telnetlib", "uu", "xdrlib"}


def local_module(name: str, roots: tuple[Path, ...]) -> Path | None:
    for root in roots:
        base = root.joinpath(*name.split("."))
        for candidate in (base.with_suffix(".py"), base / "__init__.py"):
            if candidate.is_file():
                return candidate
    return None


def image_imports(entries, roots):
    """Follow local imports from the entry points; return outside imports by module.

    Each result maps a top-level module name to (file, imported name, inside a
    function) records. Imports inside functions are followed too, so the
    closure is a superset of what actually loads.
    """
    seen, queue, found = set(), [ROOT / entry for entry in entries], {}
    while queue:
        path = queue.pop()
        if path in seen:
            continue
        seen.add(path)
        tree = ast.parse(path.read_text(), str(path))
        functions = {id(node) for function in ast.walk(tree)
                     if isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef))
                     for node in ast.walk(function)}
        search = (path.parent,) + tuple(roots)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level:
                base = path.parent
                for _ in range(node.level - 1):
                    base = base.parent
                module = base.joinpath(*node.module.split(".")) if node.module else base
                for candidate in [module.with_suffix(".py"), module / "__init__.py"] + [
                        module / (alias.name + ".py") for alias in node.names]:
                    if candidate.is_file():
                        queue.append(candidate)
                continue
            elif isinstance(node, ast.ImportFrom):
                names = [node.module]
                queue.extend(found_path for alias in node.names
                             if (found_path := local_module(f"{node.module}.{alias.name}", search)))
            else:
                continue
            for name in names:
                local = local_module(name, search)
                if local is not None:
                    queue.append(local)
                    continue
                top = name.split(".")[0]
                if top in sys.stdlib_module_names and top not in REMOVED_IN_313:
                    continue
                relative = str(path.relative_to(ROOT))
                found.setdefault(top, set()).add((relative, name, id(node) in functions))
    return found


class ImageImportTests(unittest.TestCase):
    def test_image_side_code_uses_only_the_standard_library_and_bridge(self):
        found = image_imports(ENTRY_POINTS, SEARCH_ROOTS)
        for top, uses in sorted(found.items()):
            for path, name, in_function in sorted(uses):
                with self.subTest(module=name, file=path):
                    if top == "arduino":
                        self.assertIn(name, APP_LAB)
                    else:
                        self.assertIn(top, FALLBACKS, "image-side code imports a package the "
                                      "base image may change or drop; use the standard library")
                        self.assertIn(path, FALLBACKS[top])
                        self.assertTrue(in_function, "keep fallback imports inside the function "
                                        "that needs them")
        # Keep the allowlist honest: every fallback must still be needed.
        for top, paths in FALLBACKS.items():
            used = {path for path, _name, _inside in found.get(top, ())}
            self.assertEqual(used, paths, top)

    def test_guard_reports_packages_and_removed_modules(self):
        import tempfile
        with tempfile.TemporaryDirectory(dir=ROOT / "tests") as directory:
            folder = Path(directory)
            (folder / "entry.py").write_text(
                "import json\nimport requests\nfrom helper import run\n"
                "from arduino.app_utils import Bridge\n")
            (folder / "helper.py").write_text("def run():\n    import telnetlib\n")
            found = image_imports([str((folder / "entry.py").relative_to(ROOT))], (folder,))
        self.assertEqual(set(found), {"requests", "arduino", "telnetlib"})
        self.assertEqual({inside for _path, _name, inside in found["telnetlib"]}, {True})
        self.assertEqual({name for _path, name, _inside in found["arduino"]}, {"arduino.app_utils"})


if __name__ == "__main__":
    unittest.main()

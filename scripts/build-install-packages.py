#!/usr/bin/env python3
# Project: VirtualGlove
# File: scripts/build-install-packages.py
# Purpose: Build validated versioned installers and checksums for every target machine.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-11 - Exercised the setup loader against each extracted release before publishing.
#   2026-09-09 - Added a separate Engineering Tools release asset.
#   2026-09-04 - Added versioned two-machine installation packages.
# Full history: docs/CHANGELOG.md and Git history.

"""Build release assets after generating the public PDFs and App Lab ZIP."""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def load_installer():
    """Reuse installation-time archive validation before distributing any package."""
    spec = importlib.util.spec_from_file_location("package_installer", ROOT / "scripts/install-package.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build(version, destination):
    """Create target packages from the verified App Lab bundle and emit checksums."""
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}", version):
        raise ValueError("Use a release tag without slashes or whitespace")
    import runpy
    generator = runpy.run_path(str(ROOT / "scripts/build-installer-scripts.py"))
    for machine in ("uno-q", "retropie", "recalbox", "batocera"):
        if (ROOT / ("scripts/install-" + machine + ".sh")).read_text() != generator["render"](machine):
            raise ValueError("Regenerate installer scripts before packaging")
    archive = ROOT / "output/app-lab/VirtualGlove-Uno-Q.zip"
    errors = runpy.run_path(str(ROOT / "scripts/verify-app-lab-package.py"))["archive_errors"](archive)
    if errors:
        raise ValueError("\n".join(errors))
    destination.mkdir(parents=True, exist_ok=True)
    assets = []
    with zipfile.ZipFile(archive) as original:
        for machine, name in (("uno-q", "Uno-Q"), ("retropie", "RetroPie"),
                              ("recalbox", "Recalbox"), ("batocera", "Batocera"),
                              ("launchbox", "LaunchBox")):
            output = destination / ("VirtualGlove-" + name + ".zip")
            with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as package:
                for item in original.infolist():
                    relative = Path(item.filename).parts[1:]
                    if not relative or relative == ("install-release.json",):
                        continue
                    if machine == "retropie" and relative[0] not in (
                            "scripts", "src", "retropie", "config", "native", "licenses", "LICENSE", "THIRD_PARTY_NOTICES.md"):
                        continue
                    if machine == "recalbox" and relative[0] not in (
                            "scripts", "src", "recalbox", "config", "python", "native", "licenses",
                            "LICENSE", "THIRD_PARTY_NOTICES.md"):
                        continue
                    if machine == "batocera" and relative[0] not in (
                            "scripts", "src", "recalbox", "batocera", "config", "python",
                            "native", "licenses", "LICENSE", "THIRD_PARTY_NOTICES.md"):
                        continue
                    if machine == "launchbox" and relative[0] not in (
                            "scripts", "src", "launchbox", "config", "native", "licenses",
                            "LICENSE", "THIRD_PARTY_NOTICES.md", "pyproject.toml"):
                        continue
                    if machine == "uno-q" and relative[0] == "native":
                        continue
                    if (machine == "retropie" and relative[0] == "native"
                            and (len(relative) < 2 or relative[1] not in (
                                "retropie", "nestopia-powerglove", "powerglove-dot"))):
                        continue
                    if (machine == "recalbox" and relative[0] == "native"
                            and (len(relative) < 2 or relative[1] not in (
                                "recalbox", "nestopia-powerglove"))):
                        continue
                    if (machine == "launchbox" and relative[0] == "native"
                            and (len(relative) < 2 or relative[1] not in (
                                "launchbox", "nestopia-powerglove"))):
                        continue
                    if (machine == "batocera" and relative[0] == "native"
                            and (len(relative) < 2 or relative[1] not in (
                                "batocera", "nestopia-powerglove"))):
                        continue
                    package.writestr(copy.copy(item), original.read(item.filename))
                package.writestr("VirtualGlove/install-release.json", json.dumps(
                    {"format": 1, "machine": machine, "version": version}) + "\n")
            if machine == "launchbox":
                with zipfile.ZipFile(output) as launchbox_package:
                    required = {
                        "VirtualGlove/launchbox/install-launchbox.ps1",
                        "VirtualGlove/launchbox/virtualglove-restart-runtime.cmd",
                        "VirtualGlove/launchbox/configure-launchbox-emulator.ps1",
                        "VirtualGlove/native/launchbox/manifest.json",
                        "VirtualGlove/native/launchbox/x86_64/nestopia_powerglove_libretro.dll",
                        "VirtualGlove/native/launchbox/x86_64/nestopia-powerglove-source.tar.gz",
                    }
                    missing = sorted(required - set(launchbox_package.namelist()))
                if missing:
                    raise ValueError("Build and import the LaunchBox native core: " + ", ".join(missing))
                assets.append(output)
                continue
            with tempfile.TemporaryDirectory() as directory:
                installer = load_installer()
                source = installer.unpack(output, Path(directory), machine, version)
                before = {path.relative_to(source) for path in source.rglob("*")}
                installer.load_setup(source)
                after = {path.relative_to(source) for path in source.rglob("*")}
                if after != before:
                    generated = ", ".join(sorted(str(path) for path in after - before))
                    raise ValueError("Installer setup loading mutated release staging: " + generated)
            assets.append(output)
    for name in ("install-uno-q.sh", "install-retropie.sh", "install-recalbox.sh",
                 "install-batocera.sh", "install-package.py"):
        target = destination / name
        shutil.copy2(str(ROOT / "scripts" / name), str(target))
        assets.append(target)
    engineering_builder = runpy.run_path(str(ROOT / "scripts/build-engineering-tools-package.py"))
    engineering = engineering_builder["build"](
        version, destination / "VirtualGlove-Engineering-Tools.zip"
    )
    assets.extend((engineering, engineering.with_suffix(engineering.suffix + ".sha256")))
    lines = []
    for path in assets:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        lines.append(digest.hexdigest() + "  " + path.name)
    (destination / "SHA256SUMS").write_text("\n".join(lines) + "\n")
    print("Validated release assets: " + str(destination))


def main():
    """Build explicit release assets without publishing or creating a Git tag."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True, help="Exact release tag, including development prerelease tags")
    parser.add_argument("--output", type=Path, default=ROOT / "output/install")
    args = parser.parse_args()
    build(args.version, args.output)


if __name__ == "__main__":
    main()

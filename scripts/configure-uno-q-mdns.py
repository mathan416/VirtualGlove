# Project: VirtualGlove
# File: scripts/configure-uno-q-mdns.py
# Purpose: Resolve .local names through the host Avahi socket inside App Lab containers.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-11 - Standardized App Lab container names under the virtualglove project.
#   2026-09-03 - Added persistent host mDNS resolution without pinned IP addresses.
#   2026-09-04 - Repaired persistent profile transport and asynchronous queue acknowledgements.
# Full history: docs/CHANGELOG.md and Git history.

"""Preserve resolver and UDP profile bricks when updating generated Compose output."""
import json
import re
import sys
from pathlib import Path


COMPOSE_PROJECT = "virtualglove"


def configure_project_name(text):
    """Return Compose text with one stable VirtualGlove project name."""
    matches = list(re.finditer(r"(?m)^name:[^\n]*(?:\n|$)", text))
    if len(matches) > 1:
        raise ValueError("Expected at most one top-level Compose project name")
    line = "name: " + COMPOSE_PROJECT + "\n"
    if not matches:
        return line + text
    match = matches[0]
    return text[:match.start()] + line + text[match.end():]


def configure_web_ports(text):
    """Publish the same web server on 80 and 8088 in the app-owned container.

    Keeping port 80 in the main service, rather than a separate host helper,
    makes App Lab stop release both browser ports together.
    """
    lines = text.splitlines(keepends=True)
    dashboard = next((index for index, line in enumerate(lines)
                      if line.strip() == "- 8088:8088"), None)
    if dashboard is None:
        raise ValueError("Expected app port 8088 in Compose configuration")
    if any(line.strip().startswith("- 80:") and line.strip() != "- 80:8088"
           for line in lines):
        raise ValueError("Port 80 is already assigned to another Compose destination")
    indent = lines[dashboard][:len(lines[dashboard]) - len(lines[dashboard].lstrip())]
    for mapping in ("80:8088", "8443:8443"):
        entry = indent + "- " + mapping + "\n"
        if not any(line.strip() == entry.strip() for line in lines):
            lines.insert(dashboard + 1, entry)
            dashboard += 1
    return "".join(lines)


def configure(path, project_only=False):
    """Preserve existing settings while supporting deployment before App Lab regeneration."""
    text = configure_web_ports(configure_project_name(path.read_text()))
    if project_only:
        path.write_text(text)
        return
    for name in ("avahi_resolver", "profile_control"):
        relative = "bricks/local/" + name + "/brick_compose.yaml"
        if relative in text:
            continue
        brick = path.resolve().parents[1] / relative
        entry = "- " + json.dumps(str(brick)) + "\n"
        if "include:\n" in text:
            text = text.replace("include:\n", "include:\n" + entry, 1)
        else:
            text += "\ninclude:\n" + entry
    if "target: /run/avahi-daemon" in text:
        path.write_text(text)
        return
    anchor = "    volumes:\n"
    if text.count(anchor) != 1:
        raise ValueError("Expected one App Lab main-service volumes section")
    block = ("    - type: bind\n      source: /run/avahi-daemon\n"
             "      target: /run/avahi-daemon\n      read_only: true\n")
    path.write_text(text.replace(anchor, anchor + block, 1))


if __name__ == "__main__":
    configure(Path(sys.argv[1]), project_only="--project-only" in sys.argv[2:])

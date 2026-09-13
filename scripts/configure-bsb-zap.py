#!/usr/bin/env python3
# Project: VirtualGlove
# File: scripts/configure-bsb-zap.py
# Purpose: Check and configure Bad Street Brawler's FCEUmm Glove Zap option.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-04 - Added repeatable game-option setup with emulator preflight and backups.
# Full history: docs/CHANGELOG.md and Git history.

"""Check standard RetroPie configuration; --apply enables this game's Glove Zap."""

import argparse
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

OPTION = 'fceumm_up_down_allowed'
ASSIGN = re.compile(r'^\s*([\w-]+)\s*=\s*"([^"\n]*)"\s*(?:#.*)?$')


def settings(path):
    """Read quoted RetroArch/RetroPie assignments without executing their contents."""
    result = {}
    if path.is_file():
        for line in path.read_text().splitlines():
            match = ASSIGN.match(line)
            if match:
                result.setdefault(*match.groups())
    return result


def enabled_text(text):
    """Replace only the opposing-directions option, eliminating duplicate assignments."""
    lines = [line for line in text.splitlines()
             if not re.match(r'^\s*' + OPTION + r'\s*=', line)]
    return '\n'.join(lines + [OPTION + ' = "enabled"']) + '\n'


def plan(rom, prefix, options_dir):
    """Validate installed emulator selection and choose the inherited options source."""
    if not rom.is_file() or rom.suffix.lower() not in ('.nes', '.zip', '.7z'):
        raise ValueError('Provide the installed Bad Street Brawler .nes, .zip, or .7z ROM with --rom.')
    if 'badstreetbrawler' not in re.sub(r'[^a-z]', '', rom.stem.lower()):
        raise ValueError('This helper only configures Bad Street Brawler.')
    core = prefix / 'libretrocores/lr-fceumm/fceumm_libretro.so'
    binary = prefix / 'emulators/retroarch/bin/retroarch'
    if not core.is_file() or not binary.is_file():
        raise ValueError('FCEUmm/RetroArch is missing. Install lr-fceumm using RetroPie Setup, then rerun.')
    configs = prefix / 'configs'
    system = settings(configs / 'nes/emulators.cfg')
    games = settings(configs / 'all/emulators.cfg')
    key = re.sub(r'[^a-zA-Z0-9_-]', '', 'nes_' + rom.stem)
    legacy = 'a' + hashlib.md5(('nes' + str(rom) + '\n').encode()).hexdigest()
    selected = games.get(legacy) or games.get(key) or system.get('default')
    if selected != 'lr-fceumm' or str(core) not in system.get('lr-fceumm', ''):
        raise ValueError('Game selects %s. Choose lr-fceumm for this ROM in the launch menu, then rerun.' % selected)
    # This helper supports the standard RetroPie layout; custom redirects need review.
    config_paths = [configs / 'nes/retroarch.cfg', configs / 'all/retroarch.cfg',
                    options_dir / 'FCEUmm.cfg', options_dir / (rom.parent.name + '.cfg'),
                    options_dir / (rom.stem + '.cfg'), Path(str(rom) + '.cfg')]
    global_options = configs / 'all/retroarch-core-options.cfg'
    for path in config_paths:
        values = settings(path)
        if values.get('game_specific_options') == 'false':
            raise ValueError('Enable Load Content Specific Core Options Automatically in RetroArch: ' + str(path))
        for key, expected in [('core_options_path', global_options), ('rgui_config_directory', options_dir.parent)]:
            value = values.get(key)
            if value and value != 'default' and Path(value).expanduser().resolve() != expected.resolve():
                raise ValueError('Custom %s in %s requires manual configuration; no files changed.' % (key, path))
    target = options_dir / (rom.stem + '.opt')
    sources = [target, options_dir / (rom.parent.name + '.opt'), options_dir / 'FCEUmm.opt', global_options]
    source = next((p for p in sources if p.is_file()), None)
    if source is None:
        raise ValueError('No existing FCEUmm options found. Launch and exit FCEUmm once, then rerun.')
    text = source.read_text()
    if source == global_options:
        text = '\n'.join(line for line in text.splitlines() if re.match(r'^\s*fceumm_\w+\s*=', line)) + '\n'
        if not text.strip():
            raise ValueError('No FCEUmm options in the global file. Launch and exit FCEUmm once.')
    return target, source, enabled_text(text)


def apply(target, content):
    """Back up and atomically update one options file, retaining ownership and permissions."""
    if target.is_symlink():
        raise ValueError('Refusing to replace a symlink: ' + str(target))
    target.parent.mkdir(parents=True, exist_ok=True)
    backup = Path(tempfile.mkdtemp(prefix='virtualglove-bsb-backup-', dir=str(target.parent)))
    if target.exists():
        shutil.copy2(target, backup / target.name)
        (backup / 'RESTORE.txt').write_text('Restore the saved .opt file to: ' + str(target) + '\n')
    else:
        (backup / 'RESTORE.txt').write_text('File did not exist. To undo this change, remove: ' + str(target) + '\n')
    fd, name = tempfile.mkstemp(prefix='.virtualglove-bsb-', dir=str(target.parent))
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write(content)
        owner = target.stat() if target.exists() else target.parent.stat()
        os.chmod(name, (owner.st_mode & 0o777) if target.exists() else 0o644)
        if os.geteuid() == 0:
            os.chown(name, owner.st_uid, owner.st_gid)
        os.replace(name, target)
    finally:
        if os.path.exists(name):
            os.unlink(name)
    if settings(target).get(OPTION) != 'enabled':
        raise ValueError('Readback failed; restore from ' + str(backup))
    return backup


def main(argv=None):
    """Print actionable checks; write only when --apply is explicitly requested."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom', type=Path, required=True, help='Exact installed Bad Street Brawler ROM/archive path')
    parser.add_argument('--prefix', type=Path, default=Path('/opt/retropie'), help='RetroPie installation root')
    parser.add_argument('--options-dir', type=Path, help='FCEUmm options directory, for a custom config location')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--apply', action='store_true', help='Back up and update the game options')
    mode.add_argument('--check', action='store_true', help='Read-only check (default)')
    args = parser.parse_args(argv)
    try:
        directory = args.options_dir or args.prefix / 'configs/all/retroarch/config/FCEUmm'
        target, source, content = plan(args.rom, args.prefix, directory)
        print('PASS  FCEUmm and RetroArch installed; lr-fceumm selected for this ROM.')
        print('INFO  Game options: ' + str(target))
        if target.exists() and settings(target).get(OPTION) == 'enabled':
            print('PASS  Glove Zap option already enabled; no changes needed.')
            return 0
        if not args.apply:
            print('ACTION  Rerun with --apply to enable Glove Zap. Base options: ' + str(source))
            return 2
        running = subprocess.run(['pgrep', '-x', 'retroarch'], stdout=subprocess.DEVNULL, check=False)
        if running.returncode != 1:
            raise ValueError('Exit RetroArch before applying, so it cannot overwrite the update.')
        backup = apply(target, content)
        print('PASS  Game option enabled and read back. Backup: ' + str(backup))
        print('ACTION  Relaunch the game; confirm options loading and test Glove Zap in live play.')
        return 0
    except (OSError, ValueError) as error:
        print('ACTION  ' + str(error))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())

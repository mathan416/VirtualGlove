"""Install the shared console link without altering RetroArch configuration."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
import tempfile
from pathlib import Path
from .pairing_console import LinkStore, default_root, platform_name, open_window, ensure_certificate
from .pairing import write_private

VERSION = '0.3.0'


def _install(app, descriptor, *, root=None, execute=True):
    root = Path(root or default_root())
    store = LinkStore(root)
    if app is not None:
        store.register(app, descriptor)
    software = root.parent / 'software'
    software.mkdir(parents=True, exist_ok=True)
    source = Path(__file__).resolve().parent
    installed_version = software / 'VERSION'
    current = tuple(map(int, installed_version.read_text().strip().split('.'))) if installed_version.exists() else ()
    launcher = root.parent / 'pair-console'
    if current > tuple(map(int, VERSION.split('.'))) and launcher.exists():
        # Registering a product must not replace a newer helper or service unit.
        # Restart the existing service so it reloads the adapter registry.
        if execute:
            platform = platform_name()
            commands = {'retropie': ['systemctl', 'restart', 'controller-router-link.service'],
                        'batocera': ['batocera-services', 'restart', 'ControllerRouterLink']}
            if platform in commands:
                subprocess.run(commands[platform], check=True)
            elif platform == 'recalbox':
                service = str(root.parent / 'link-service')
                subprocess.run(['sh', service, 'stop'], check=True)
                subprocess.run(['sh', service, 'start'], check=True)
            elif platform == 'launchbox':
                pid = root / 'service.pid'
                if pid.exists() and pid.read_text().strip().isdigit():
                    subprocess.run(['taskkill', '/PID', pid.read_text().strip(), '/F'],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                subprocess.Popen([sys.executable, '-m', 'router_shared.pairing_console', 'serve', '--root', str(root)],
                    cwd=software, creationflags=subprocess.CREATE_NO_WINDOW,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return launcher
    if current <= tuple(map(int, VERSION.split('.'))):
        for item in source.rglob('*'):
            if not item.is_file() or '__pycache__' in item.parts or item.suffix == '.pyc':
                continue
            target = software / 'router_shared' / item.relative_to(source)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)
        write_private(installed_version, (VERSION + '\n').encode())
    content = ('#!/bin/sh\nif [ "$(id -u)" != 0 ]; then exec sudo -- "$0" "$@"; fi\ncd ' + _quote(str(software)) + '\nexec ' + _quote(sys.executable) +
               ' -m router_shared.pairing_console pair --root ' + _quote(str(root)) + '\n')
    write_private(launcher, content.encode())
    launcher.chmod(0o755)
    platform = platform_name()
    if execute:
        ensure_certificate(root)
    command = _quote(sys.executable) + ' -m router_shared.pairing_console serve --root ' + _quote(str(root))
    if platform == 'retropie':
        unit = Path('/etc/systemd/system/controller-router-link.service')
        write_private(unit, ('[Unit]\nDescription=Controller Router console connection\nAfter=network.target\n'
            '[Service]\nWorkingDirectory=' + str(software) + '\nExecStart=' + command +
            '\nRestart=on-failure\nRestartSec=2\nUMask=0077\n[Install]\nWantedBy=multi-user.target\n').encode())
        unit.chmod(0o644)
        if execute:
            subprocess.run(['systemctl', 'daemon-reload'], check=True)
            subprocess.run(['systemctl', 'reset-failed', 'controller-router-link.service'], check=False,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(['systemctl', 'enable', '--now', 'controller-router-link.service'], check=True)
            subprocess.run(['systemctl', 'restart', 'controller-router-link.service'], check=True)
    elif platform == 'batocera':
        service = Path('/userdata/system/services/ControllerRouterLink')
        script = '#!/bin/sh\ncase "$1" in\nstart) cd ' + _quote(str(software)) + '; ' + command + \
            ' >/dev/null 2>&1 & echo $! > ' + _quote(str(root / 'service.pid')) + ';;\nstop) if [ -f ' + \
            _quote(str(root / 'service.pid')) + ' ]; then kill "$(cat ' + _quote(str(root / 'service.pid')) + \
            ')" 2>/dev/null || true; for retry in 1 2 3 4 5; do kill -0 "$(cat ' + _quote(str(root / 'service.pid')) + ')" 2>/dev/null || break; sleep 1; done; rm -f ' + _quote(str(root / 'service.pid')) + '; fi;;\nesac\n'
        write_private(service, script.encode()); service.chmod(0o755)
        if execute:
            subprocess.run(['batocera-services', 'enable', 'ControllerRouterLink'], check=True)
            subprocess.run(['batocera-services', 'restart', 'ControllerRouterLink'], check=True)
    elif platform == 'recalbox':
        service = root.parent / 'link-service'
        pid = _quote(str(root / 'service.pid'))
        script = ('#!/bin/sh\ncase "$1" in\nstart) if [ -f ' + pid +
            ' ] && kill -0 "$(cat ' + pid + ')" 2>/dev/null; then exit 0; fi\ncd ' +
            _quote(str(software)) + '\n' + command + ' >/dev/null 2>&1 &;;\nstop) if [ -f ' + pid +
            ' ]; then kill "$(cat ' + pid + ')" 2>/dev/null || true; for retry in 1 2 3 4 5; do kill -0 "$(cat ' + _quote(str(root / 'service.pid')) + ')" 2>/dev/null || break; sleep 1; done; rm -f ' + pid + '; fi;;\nesac\n')
        write_private(service, script.encode()); service.chmod(0o755)
        custom = Path('/recalbox/share/system/custom.sh')
        source = custom.read_text() if custom.exists() else '#!/bin/sh\n'
        begin, end = '# BEGIN Controller Router connection', '# END Controller Router connection'
        block = begin + '\ncase "$1" in\nstart) sh ' + _quote(str(service)) + ' start;;\nstop) sh ' + _quote(str(service)) + ' stop;;\nesac\n' + end
        import re
        updated, found = re.subn(re.escape(begin) + r'.*?' + re.escape(end), lambda _: block, source, flags=re.S)
        write_private(custom, ((updated if found else source.rstrip() + '\n' + block) + '\n').encode())
        custom.chmod(0o755)
        if execute:
            subprocess.run(['sh', str(service), 'stop'], check=True)
            subprocess.run(['sh', str(service), 'start'], check=True)
    elif platform == 'launchbox':
        startup = Path(os.environ['APPDATA']) / 'Microsoft/Windows/Start Menu/Programs/Startup/ControllerRouter.cmd'
        command_line = subprocess.list2cmdline([sys.executable, '-m', 'router_shared.pairing_console', 'serve', '--root', str(root)])
        write_private(startup, ('@echo off\ncd /d "' + str(software) + '"\nstart "Controller Router" /b ' + command_line + ' >nul 2>&1\n').encode())
        if execute:
            pid = root / 'service.pid'
            if pid.exists() and pid.read_text().strip().isdigit():
                subprocess.run(['taskkill', '/PID', pid.read_text().strip(), '/F'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.Popen([sys.executable, '-m', 'router_shared.pairing_console', 'serve', '--root', str(root)],
                             cwd=software, creationflags=subprocess.CREATE_NO_WINDOW,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        raise ValueError('The shared link installer needs a supported console service adapter.')
    if execute:
        from .pairing import Peer, fingerprint
        import ssl
        cert, _ = ensure_certificate(root)
        pin = fingerprint(ssl.PEM_cert_to_DER_cert(cert.read_text()))
        for attempt in range(20):
            try:
                identity = Peer('console.local', pin=pin, resolve=lambda _: '127.0.0.1').request('/identity')
                if identity.get('console_id') != store.console_id:
                    raise ValueError('Unexpected console identity.')
                break
            except (OSError, ValueError):
                if attempt == 19:
                    raise RuntimeError('The shared console connection service did not become ready. Check its service status before pairing.') from None
                time.sleep(0.5)
        if not store.connection:
            open_window(root)
    return launcher


def install(app, descriptor, *, root=None, execute=True):
    """Retain installed service files and private settings if an upgrade fails."""
    root = Path(root or default_root())
    root.parent.mkdir(parents=True, exist_ok=True)
    platform = platform_name()
    paths = [root / 'adapters.json', root.parent / 'software', root.parent / 'pair-console']
    if platform == 'retropie':
        paths.append(Path('/etc/systemd/system/controller-router-link.service'))
        restart = ['systemctl', 'restart', 'controller-router-link.service']
    elif platform == 'batocera':
        paths.append(Path('/userdata/system/services/ControllerRouterLink'))
        restart = ['batocera-services', 'restart', 'ControllerRouterLink']
    elif platform == 'recalbox':
        paths.extend([root.parent / 'link-service', Path('/recalbox/share/system/custom.sh')])
        restart = ['sh', str(root.parent / 'link-service'), 'start']
    else:
        restart = None
        if platform == 'launchbox':
            paths.append(Path(os.environ['APPDATA']) / 'Microsoft/Windows/Start Menu/Programs/Startup/ControllerRouter.cmd')
    previous_software = (root.parent / 'software').exists()
    with tempfile.TemporaryDirectory(prefix='.link-upgrade-', dir=str(root.parent)) as temporary:
        backup = Path(temporary)
        saved = []
        for index, path in enumerate(paths):
            copy = backup / str(index)
            if path.is_dir():
                shutil.copytree(path, copy)
            elif path.is_file():
                shutil.copy2(path, copy)
            saved.append((path, copy))
        try:
            return _install(app, descriptor, root=root, execute=execute)
        except BaseException:
            for path, copy in saved:
                if path.is_dir():
                    shutil.rmtree(path)
                elif path.exists():
                    path.unlink()
                if copy.is_dir():
                    shutil.copytree(copy, path)
                elif copy.is_file():
                    path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(copy, path)
            if execute and previous_software and restart:
                if platform == 'retropie':
                    subprocess.run(['systemctl', 'daemon-reload'], check=False)
                subprocess.run(restart, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            raise


def _quote(value):
    import shlex
    return shlex.quote(value)


def main():
    import argparse, json
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app', choices=('virtualglove', 'rob_vision'), required=True)
    parser.add_argument('--descriptor', type=Path, required=True)
    args = parser.parse_args()
    install(args.app, json.loads(args.descriptor.read_text(encoding='utf-8-sig')))


if __name__ == '__main__':
    main()

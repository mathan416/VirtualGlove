"""Run both controller Linux services without starting either App Lab sketch."""
from __future__ import annotations

import json
import os
import secrets
import stat
import subprocess
from pathlib import Path

ROOT = Path("/home/arduino/ArduinoApps")
RUNTIME = Path("/home/arduino/.local/share/controller-router-portal/runtime")
SOCKET_DIR = Path("/run/user/1000/controller-router-portal")
PRODUCTS = ("virtualglove", "rob-vision")
IMAGE = "ghcr.io/arduino/app-bricks/python-apps-base:0.13.2"
BASE_REPOSITORY = IMAGE.rsplit(":", 1)[0]
APP_LAB_PROJECTS = ("virtualglove", "rob-vision")


def _base_version(tag: str) -> tuple[int, ...] | None:
    try:
        return tuple(int(part) for part in tag.split("."))
    except ValueError:
        return None


def clean_compose(name: str) -> dict:
    """Compose a first install without asking App Lab to flash a product sketch."""
    root = ROOT / name
    addresses = subprocess.check_output(["hostname", "-I"], text=True).split()
    host_ip = next((address for address in addresses if ":" not in address and
                    not address.startswith("127.")), "127.0.0.1")
    ports = (["127.0.0.1:8088:8088", "8100:8088", "8443:8443"]
             if name == "virtualglove" else ["8766:8766", "8101:8766"])
    volumes = [{"type": "bind", "source": str(root), "target": "/app"},
               {"type": "bind", "source": "/dev", "target": "/dev"},
               {"type": "bind", "source": "/run/udev", "target": "/run/udev", "read_only": True},
               {"type": "bind", "source": "/run/arduino-router.sock", "target": "/run/arduino-router.sock"}]
    main = {"image": IMAGE, "entrypoint": "/run.sh", "restart": "unless-stopped",
            "user": "1000:1000", "group_add": ["44", "29", "991", "20", "1001"],
            "device_cgroup_rules": ["c 226:* rmw", "c 251:* rmw", "c 505:* rmw",
                                    "c 81:* rmw", "c 116:* rmw"],
            "ports": ports, "volumes": volumes,
            "extra_hosts": ["msgpack-rpc-router:host-gateway"],
            "environment": {"APP_HOME": str(root), "BOARD_NAME": "unoq",
                            "HOST_IP": host_ip,
                            "MODELS_PATH": "/var/lib/arduino-app-cli/models",
                            "XDG_RUNTIME_DIR": "/run/user/1000"}}
    resolver = {"image": IMAGE, "entrypoint": ["python3", "/resolver_service.py"],
                "restart": "unless-stopped", "user": "1000:1000", "network_mode": "none",
                "read_only": True, "cap_drop": ["ALL"],
                "security_opt": ["no-new-privileges:true"],
                "volumes": [{"type": "bind", "source": "/run/avahi-daemon", "target": "/run/avahi-daemon", "read_only": True},
                            {"type": "bind", "source": str(root / "data"), "target": "/app/data"},
                            {"type": "bind", "source": str(root / "scripts/avahi-resolver-service.py"),
                             "target": "/resolver_service.py", "read_only": True}]}
    services = {"main": main, "avahi-resolver": resolver}
    if name == "virtualglove":
        main["depends_on"] = {"avahi-resolver": {"condition": "service_started"},
                              "profile-relay": {"condition": "service_started"}}
        services["profile-relay"] = {"image": IMAGE, "entrypoint": ["python3", "/profile-relay.py"],
            "restart": "unless-stopped", "user": "1000:1000", "ports": ["55356:55356/udp"],
            "volumes": [{"type": "bind", "source": str(root / "scripts/profile-relay.py"),
                         "target": "/profile-relay.py", "read_only": True}]}
    else:
        main["depends_on"] = {"avahi-resolver": {"condition": "service_started"}}
    return {"name": name + "-runtime", "services": services}


def ensure_socket_directory() -> None:
    """Create the private bind source before products or the broker start."""
    try:
        SOCKET_DIR.mkdir(mode=0o700)
    except FileExistsError:
        pass
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    fd = os.open(str(SOCKET_DIR), flags)
    try:
        info = os.fstat(fd)
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
            raise RuntimeError("Router socket directory is not owned by the current user")
        os.fchmod(fd, 0o700)
    finally:
        os.close(fd)


def _stale_led_bind(volume: object) -> bool:
    """Recognize an optional App Lab LED mount left behind by a kernel update."""
    if not isinstance(volume, dict) or volume.get("type") != "bind":
        return False
    source, target = volume.get("source"), volume.get("target")
    led_class = "/sys/class/leds/"
    return (isinstance(source, str) and isinstance(target, str)
            and source.startswith(led_class) and target.startswith(led_class)
            and not Path(source).exists())


def product_compose(name: str) -> Path:
    if name not in PRODUCTS:
        raise ValueError("Unknown controller product")
    source = ROOT / name / ".cache/app-compose.yaml"
    if source.is_file():
        env = dict(os.environ, APP_HOME=str(ROOT / name))
        result = subprocess.run(["docker", "compose", "-f", str(source), "config", "--format", "json"],
                                env=env, check=True, text=True, capture_output=True)
        config = json.loads(result.stdout)
    else:
        config = clean_compose(name)
    ensure_socket_directory()
    config["name"] = name + "-runtime"
    # Cached App Lab Compose files retain the old project's network name.
    # Give each continuously running service its own Router-managed network.
    config.setdefault("networks", {}).setdefault("default", {})["name"] = name + "-runtime_default"
    for service in config["services"].values():
        # App Lab's cache keeps the base image of the App Lab release that
        # wrote it. Run every product service on the Router's one base image so
        # an App Lab update never leaves a second ~900 MB image in use.
        if str(service.get("image", "")).startswith(BASE_REPOSITORY + ":"):
            service["image"] = IMAGE
        labels = service.get("labels", {})
        if isinstance(labels, dict):
            service["labels"] = {key: value for key, value in labels.items()
                                 if not key.startswith("cc.arduino.app")}
    main = config["services"]["main"]
    # App Lab writes this cache only after a successful MCU upload. If an
    # upload fails following a kernel update, optional LED paths from the old
    # kernel can prevent the independent product containers from starting.
    # Filter the Router runtime copy; leave App Lab's own cache intact.
    main["volumes"] = [volume for volume in main.get("volumes", [])
                       if not _stale_led_bind(volume)]
    main.setdefault("volumes", []).append({"type": "bind",
        "source": str(SOCKET_DIR),
        "target": "/run/user/1000/controller-router-portal"})
    RUNTIME.mkdir(parents=True, exist_ok=True)
    target = RUNTIME / f"{name}.json"
    temporary = target.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(config, indent=2) + "\n")
    temporary.chmod(0o600)
    os.replace(temporary, target)
    return target


def start(name: str) -> None:
    data = ROOT / name / 'data'
    if (ROOT / name / 'app.yaml').exists():
        data.mkdir(parents=True, exist_ok=True)
        capability = data / 'router-pairing-adapter-token'
        if not capability.exists():
            capability.write_text(secrets.token_urlsafe(48) + '\n')
            capability.chmod(0o600)
    root = ROOT / name
    data = root / "data"
    data.mkdir(parents=True, exist_ok=True)
    marker = data / "controller-router-required"
    if not marker.exists():
        marker.write_text("1\n")
        marker.chmod(0o600)
    compose = product_compose(name)
    subprocess.run(["docker", "compose", "-p", name + "-runtime", "-f", str(compose),
                    "up", "-d", "--remove-orphans"], check=True)


def retire_old_base_images() -> list[str]:
    """Remove older python-apps-base tags that no running container still uses.

    Exited containers of the products' own App Lab projects are removed first,
    since App Lab recreates them on its next start. Docker refuses an image a
    container still uses, and nothing is forced: a refused tag stays for the
    next start. Newer tags belong to App Lab and are always kept.
    """
    current = _base_version(IMAGE.rsplit(":", 1)[1])

    def docker(*arguments: str) -> subprocess.CompletedProcess:
        return subprocess.run(["docker", *arguments], text=True, capture_output=True,
                              check=False, timeout=120)

    try:
        tags = docker("image", "ls", BASE_REPOSITORY, "--format", "{{.Tag}}").stdout.split()
        removed = []
        for tag in tags:
            version = _base_version(tag)
            if current is None or version is None or version >= current:
                continue
            image = f"{BASE_REPOSITORY}:{tag}"
            exited = docker("ps", "-a", "--filter", f"ancestor={image}",
                            "--filter", "status=exited", "--filter", "status=created",
                            "--format", '{{.ID}} {{.Label "com.docker.compose.project"}}').stdout
            stale = [line.split()[0] for line in exited.splitlines()
                     if len(line.split()) == 2 and line.split()[1] in APP_LAB_PROJECTS]
            if stale:
                docker("rm", *stale)
            if docker("image", "rm", image).returncode == 0:
                removed.append(image)
        return removed
    except (OSError, subprocess.SubprocessError):
        return []


def stop(name: str) -> None:
    compose = RUNTIME / f"{name}.json"
    if compose.is_file():
        subprocess.run(["docker", "compose", "-p", name + "-runtime", "-f", str(compose),
                        "down"], check=True)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("start", "stop", "start-all", "stop-all"))
    parser.add_argument("product", nargs="?", choices=PRODUCTS)
    options = parser.parse_args()
    if options.action.endswith("-all"):
        for product in PRODUCTS:
            if (ROOT / product / "app.yaml").is_file():
                (start if options.action == "start-all" else stop)(product)
        if options.action == "start-all":
            for image in retire_old_base_images():
                print(f"Removed unused base image {image}", flush=True)
    elif options.product:
        (start if options.action == "start" else stop)(options.product)
    else:
        parser.error("A product name is required")

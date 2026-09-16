# Project: VirtualGlove
# File: src/powerglove_vision/pairing.py
# Purpose: Provision the shared controller token through bounded TLS pairing or authenticated SSH.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-11 - Extended the single-use RetroPie pairing window to five minutes.
#   2026-09-11 - Made certificate-name validation independent of OpenSSL exit-code differences.
#   2026-09-11 - Added a persistent per-Controller authority for trusted local HTTPS.
#   2026-09-02 - Added to VirtualGlove.
#   2026-09-03 - Standardized source documentation and maintenance metadata.
# Full history: docs/CHANGELOG.md and Git history.

"""Short-lived HTTPS pairing for VirtualGlove and a supported console."""

from __future__ import annotations

import argparse
import base64
import datetime
import hashlib
import hmac
import http.client
import ipaddress
import json
import os
import secrets
import socket
import ssl
import subprocess
import tempfile
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Callable, Optional

from .resolver import resolve_ipv4
from .controller_protocol import encode_message, decode_message

CONSOLE_PLATFORMS = ("retropie", "recalbox", "batocera", "launchbox")


def console_platform() -> str:
    """Identify the installed console platform without exposing host details."""
    if os.name == "nt":
        return "launchbox"
    if Path("/recalbox/recalbox.version").is_file():
        return "recalbox"
    if Path("/usr/share/batocera/batocera.version").is_file():
        return "batocera"
    return "retropie"


PAIRING_PORT = 55357
CODE_PART_LENGTH = 10
CONTROLLER_PORT = 55355


class QuietHTTPServer(HTTPServer):
    """Suppress expected request errors during short-lived pairing sessions."""
    def handle_error(self, _request: object, _client_address: object) -> None:
        """Ignore malformed or disconnected pairing clients without noisy tracebacks."""
        return


class BoundedTLSServer(QuietHTTPServer):
    """TLS server that bounds each untrusted handshake and request."""

    def __init__(
        self, server_address: tuple[str, int], handler: type[BaseHTTPRequestHandler],
        context: ssl.SSLContext, deadline: float,
    ) -> None:
        self.tls_context = context
        self.deadline = deadline
        super().__init__(server_address, handler)

    def get_request(self) -> tuple[socket.socket, tuple[str, int]]:
        """Wrap one accepted socket in TLS while enforcing the session deadline."""
        connection, address = super().get_request()
        connection.settimeout(max(0.05, min(1.0, self.deadline - time.monotonic())))
        try:
            return self.tls_context.wrap_socket(connection, server_side=True), address
        except (OSError, ssl.SSLError):
            connection.close()
            raise


def _code_part(value: bytes) -> str:
    """Encode bytes as a short human-readable Base32 verification component."""
    return base64.b32encode(value).decode("ascii").rstrip("=")[:CODE_PART_LENGTH]


def certificate_code(pem: str) -> str:
    """Derive the certificate component of a physical pairing code."""
    der = ssl.PEM_cert_to_DER_cert(pem)
    return _code_part(hashlib.sha256(der).digest())


def certificate_identity(pem: str) -> str:
    """Short hexadecimal prefix users can compare with browser certificate details."""
    der = ssl.PEM_cert_to_DER_cert(pem)
    return hashlib.sha256(der).hexdigest()[:7].upper()


def certificate_fingerprint(pem: str) -> str:
    """Return a complete displayable SHA-256 certificate fingerprint."""
    der = ssl.PEM_cert_to_DER_cert(pem)
    digest = hashlib.sha256(der).hexdigest().upper()
    return ":".join(digest[index:index + 2] for index in range(0, len(digest), 2))


def local_ipv4_addresses() -> list[str]:
    """Find physical-host IPv4 addresses suitable for certificate SAN entries."""
    addresses: list[str] = []
    try:
        result = subprocess.check_output(
            ["ip", "-j", "-4", "address", "show", "up"], timeout=5)
        for interface in json.loads(result):
            name = str(interface.get("ifname", "")).lower()
            if name == "lo" or name.startswith(("docker", "br-", "veth", "virbr")):
                continue
            for item in interface.get("addr_info", []):
                if item.get("family") != "inet" or item.get("scope") != "global":
                    continue
                try:
                    address = ipaddress.ip_address(item.get("local", ""))
                except ValueError:
                    continue
                value = str(address)
                if (address.version == 4 and not address.is_loopback and
                        not address.is_link_local and not address.is_multicast and
                        value not in addresses):
                    addresses.append(value)
    except (OSError, ValueError, KeyError, subprocess.SubprocessError,
            json.JSONDecodeError):
        pass
    return addresses


def _valid_server_certificate(
    certificate: Path, authority: Path, hostname: str, addresses: list[str],
) -> bool:
    """Accept an unexpired leaf only when its chain and current names still match."""
    commands = [
        ["openssl", "verify", "-CAfile", str(authority), str(certificate)],
        ["openssl", "x509", "-checkend", str(30 * 24 * 60 * 60), "-noout",
         "-in", str(certificate)],
    ]
    if not all(subprocess.run(command, stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL).returncode == 0
               for command in commands):
        return False
    try:
        decoded = ssl._ssl._test_decode_cert(str(certificate))
        names = decoded.get("subjectAltName", ())
        dns_names = {value.lower() for kind, value in names if kind == "DNS"}
        ip_names = {ipaddress.ip_address(value) for kind, value in names
                    if kind == "IP Address"}
        required_addresses = {ipaddress.ip_address(value) for value in addresses}
    except (OSError, ValueError, ssl.SSLError):
        return False
    return hostname.lower() in dns_names and required_addresses.issubset(ip_names)


def _certificate_matches_key(certificate: Path, private_key: Path) -> bool:
    """Detect an interrupted leaf replacement before loading the TLS server."""
    try:
        certificate_public = subprocess.check_output([
            "openssl", "x509", "-in", str(certificate), "-pubkey", "-noout",
        ], stderr=subprocess.DEVNULL, timeout=5)
        key_public = subprocess.check_output([
            "openssl", "pkey", "-in", str(private_key), "-pubout",
        ], stderr=subprocess.DEVNULL, timeout=5)
        return hmac.compare_digest(certificate_public, key_public)
    except (OSError, subprocess.SubprocessError):
        return False


def ensure_controller_authority(
    directory: Path, hostname: str, addresses: Optional[list[str]] = None,
) -> tuple[Path, Path, str, str]:
    """Create or renew a leaf signed by one persistent private Controller authority."""
    directory.mkdir(parents=True, exist_ok=True)
    os.chmod(directory, 0o700)
    if directory.is_symlink():
        raise ValueError("refusing symbolic TLS directory")
    authority = directory / "controller-ca-cert.pem"
    authority_key = directory / "controller-ca-key.pem"
    certificate = directory / "pairing-cert.pem"
    private_key = directory / "pairing-key.pem"
    if any(path.is_symlink() for path in
           (authority, authority_key, certificate, private_key)):
        raise ValueError("refusing symbolic TLS file")
    addresses = list(addresses if addresses is not None else local_ipv4_addresses())

    with tempfile.TemporaryDirectory(prefix="controller-tls-", dir=str(directory)) as name:
        temporary = Path(name)
        if not authority.is_file() or not authority_key.is_file():
            new_authority = temporary / authority.name
            new_authority_key = temporary / authority_key.name
            subprocess.run([
                "openssl", "req", "-x509", "-newkey", "rsa:3072", "-sha256", "-nodes",
                "-days", "3650", "-subj", "/CN=VirtualGlove Controller Local Authority",
                "-addext", "basicConstraints=critical,CA:TRUE,pathlen:0",
                "-addext", "keyUsage=critical,keyCertSign,cRLSign",
                "-addext", "subjectKeyIdentifier=hash",
                "-keyout", str(new_authority_key), "-out", str(new_authority),
            ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            os.chmod(new_authority_key, 0o600)
            os.chmod(new_authority, 0o644)
            os.replace(new_authority_key, authority_key)
            os.replace(new_authority, authority)
        os.chmod(authority_key, 0o600)
        os.chmod(authority, 0o644)

        usable = (certificate.is_file() and private_key.is_file() and
                  _valid_server_certificate(certificate, authority, hostname, addresses) and
                  _certificate_matches_key(certificate, private_key))
        if not usable:
            new_certificate = temporary / certificate.name
            new_private_key = temporary / private_key.name
            request = temporary / "server.csr"
            extensions = temporary / "server.ext"
            alt_names = ["DNS.1 = " + hostname]
            alt_names.extend("IP.%d = %s" % (index, value)
                             for index, value in enumerate(addresses, 1))
            extensions.write_text(
                "[server_cert]\n"
                "basicConstraints = critical,CA:FALSE\n"
                "keyUsage = critical,digitalSignature,keyEncipherment\n"
                "extendedKeyUsage = serverAuth\n"
                "subjectKeyIdentifier = hash\n"
                "authorityKeyIdentifier = keyid,issuer\n"
                "subjectAltName = @alt_names\n"
                "[alt_names]\n" + "\n".join(alt_names) + "\n")
            subprocess.run([
                "openssl", "req", "-new", "-newkey", "rsa:2048", "-sha256", "-nodes",
                "-subj", "/CN=" + hostname, "-keyout", str(new_private_key),
                "-out", str(request),
            ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run([
                "openssl", "x509", "-req", "-sha256", "-days", "397",
                "-in", str(request), "-CA", str(authority), "-CAkey", str(authority_key),
                "-set_serial", str(secrets.randbits(127) + 1),
                "-extfile", str(extensions), "-extensions", "server_cert",
                "-out", str(new_certificate),
            ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            os.chmod(new_private_key, 0o600)
            os.chmod(new_certificate, 0o644)
            os.replace(new_private_key, private_key)
            os.replace(new_certificate, certificate)
        os.chmod(private_key, 0o600)
        os.chmod(certificate, 0o644)

    pem = certificate.read_text()
    authority_pem = authority.read_text()
    return certificate, private_key, pem, authority_pem


def normalize_pairing_code(code: str) -> tuple[str, str]:
    """Normalize user formatting and split a complete physical pairing code."""
    normalized = "".join(character for character in code.upper() if character.isalnum())
    if len(normalized) != CODE_PART_LENGTH * 2:
        raise ValueError("pairing code must contain 20 letters or numbers")
    return normalized[:CODE_PART_LENGTH], normalized[CODE_PART_LENGTH:]


def display_pairing_code(certificate_part: str, authorization_part: str) -> str:
    """Format certificate and authorization components into readable groups."""
    combined = certificate_part + authorization_part
    return "-".join(combined[index:index + 5] for index in range(0, len(combined), 5))


def generate_certificate(directory: Path, hostname: str, days: int = 1) -> tuple[Path, Path, str]:
    """Create a temporary self-signed pairing certificate and return its verification code."""
    directory.mkdir(parents=True, exist_ok=True)
    certificate = directory / "pairing-cert.pem"
    private_key = directory / "pairing-key.pem"
    try:
        subprocess.run([
            "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
            "-days", str(days), "-subj", f"/CN={hostname}",
            "-addext", f"subjectAltName=DNS:{hostname}",
            "-keyout", str(private_key), "-out", str(certificate),
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (FileNotFoundError, subprocess.CalledProcessError):
        # Stock Windows does not include the OpenSSL command. The LaunchBox
        # package installs the wheel-backed library into its isolated runtime.
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, hostname)])
        now = datetime.datetime.now(datetime.timezone.utc)
        leaf = (
            x509.CertificateBuilder()
            .subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(minutes=1))
            .not_valid_after(now + datetime.timedelta(days=days))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName(hostname)]), critical=False)
            .sign(key, hashes.SHA256())
        )
        private_key.write_bytes(key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ))
        certificate.write_bytes(leaf.public_bytes(serialization.Encoding.PEM))
    os.chmod(private_key, 0o600)
    pem = certificate.read_text()
    return certificate, private_key, pem


def install_token(token_file: Path, token: str) -> None:
    """Atomically install a validated shared token with restricted permissions."""
    if not 16 <= len(token) <= 256 or any(character.isspace() for character in token):
        raise ValueError("invalid controller token")
    token_file.parent.mkdir(parents=True, exist_ok=True)
    temporary = token_file.with_suffix(".pairing-tmp")
    temporary.write_text(token + "\n")
    os.chmod(temporary, 0o640)
    try:
        import grp
        os.chown(temporary, 0, grp.getgrnam("input").gr_gid)
    except (ImportError, KeyError, PermissionError):
        pass
    os.replace(temporary, token_file)


def serve_pairing(
    host: str,
    port: int,
    token_file: Path,
    timeout: int,
    on_paired: Callable[[], None],
    on_ready: Optional[Callable[[str, int], None]] = None,
) -> str:
    """Serve one bounded, physically authorized token request over TLS."""
    authorization = _code_part(secrets.token_bytes(16))
    paired = False
    rejected_attempts = 0
    with tempfile.TemporaryDirectory(prefix="virtualglove-pair-") as temporary_name:
        temporary = Path(temporary_name)
        certificate, private_key, pem = generate_certificate(temporary, "VirtualGlove-Console-Pairing")
        code = display_pairing_code(certificate_code(pem), authorization)

        class PairingHandler(BaseHTTPRequestHandler):
            """Accept one authenticated token transfer during the bounded pairing window."""
            def log_message(self, _format: str, *_args: object) -> None:
                return

            def do_POST(self) -> None:
                nonlocal paired, rejected_attempts
                if self.path != "/pair" or paired:
                    self.send_error(404)
                    return
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    if not 1 <= length <= 1024:
                        raise ValueError("invalid pairing request")
                    body = json.loads(self.rfile.read(length))
                    supplied = str(body.get("authorization", "")).upper()
                    if not hmac.compare_digest(supplied, authorization):
                        raise ValueError("pairing code was rejected")
                    expected_platform = str(body.get("platform", ""))
                    detected_platform = console_platform()
                    if expected_platform not in CONSOLE_PLATFORMS:
                        raise ValueError("choose a supported console platform")
                    if expected_platform != detected_platform:
                        raise ValueError(
                            "selected platform does not match this console (detected "
                            + detected_platform + ")"
                        )
                    install_token(token_file, str(body.get("token", "")))
                    paired = True
                    response = json.dumps({"paired": True,
                                           "platform": detected_platform}).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(response)))
                    self.end_headers()
                    self.wfile.write(response)
                except (ValueError, json.JSONDecodeError, OSError) as exc:
                    rejected_attempts += 1
                    response = json.dumps({"error": str(exc)}).encode()
                    self.send_response(400)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(response)))
                    self.end_headers()
                    self.wfile.write(response)

        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certificate, private_key)
        deadline = time.monotonic() + timeout
        server = BoundedTLSServer((host, port), PairingHandler, context, deadline)
        server.timeout = 0.5
        print(f"VirtualGlove pairing code: {code}", flush=True)
        print(f"This code expires in {timeout} seconds and can be used once.", flush=True)
        if on_ready is not None:
            on_ready(code, int(server.server_address[1]))
        while not paired and rejected_attempts < 5 and time.monotonic() < deadline:
            server.handle_request()
        server.server_close()
        if not paired:
            raise TimeoutError("pairing window expired")
    on_paired()
    return code


def pair_with_code(host: str, port: int, code: str, token: str,
                   platform: str, timeout: float = 8.0) -> None:
    """Verify a pinned certificate and transfer the shared token over TLS."""
    expected_certificate, authorization = normalize_pairing_code(code)
    discovery_context = ssl._create_unverified_context()
    with socket.create_connection((resolve_ipv4(host), port), timeout=timeout) as raw_connection:
        with discovery_context.wrap_socket(raw_connection, server_hostname=host) as tls_connection:
            der = tls_connection.getpeercert(binary_form=True)
    pem = ssl.DER_cert_to_PEM_cert(der)
    if not hmac.compare_digest(certificate_code(pem), expected_certificate):
        raise ValueError("pairing code does not match the console certificate")
    context = ssl.create_default_context(cadata=pem)
    context.check_hostname = False
    connection = http.client.HTTPSConnection(resolve_ipv4(host), port, timeout=timeout, context=context)
    if platform not in CONSOLE_PLATFORMS:
        raise ValueError("choose a supported console platform")
    payload = json.dumps({"authorization": authorization, "token": token,
                          "platform": platform}).encode()
    connection.request("POST", "/pair", body=payload, headers={"Content-Type": "application/json"})
    response = connection.getresponse()
    body = response.read()
    connection.close()
    if response.status != 200:
        try:
            message = json.loads(body).get("error", "pairing failed")
        except (ValueError, json.JSONDecodeError):
            message = "pairing failed"
        raise ValueError(message)
    try:
        result = json.loads(body)
    except (ValueError, json.JSONDecodeError) as exc:
        raise ValueError("pairing response did not identify the console platform") from exc
    if result.get("platform") != platform:
        raise ValueError("paired console platform did not match the saved selection")
    verify_controller_pairing(host, CONTROLLER_PORT, token)


def verify_controller_pairing(host: str, port: int, token: str, timeout: float = 4.0) -> None:
    """Confirm the receiver accepts the newly installed token after pairing."""
    address = resolve_ipv4(host)
    session = secrets.token_hex(16)
    deadline = time.monotonic() + timeout
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(0.25)
        request = secrets.token_hex(16)
        while time.monotonic() < deadline:
            sock.sendto(encode_message("hello", token, session=session, request=request),
                        (address, port))
            try:
                while time.monotonic() < deadline:
                    payload, peer = sock.recvfrom(4096)
                    if peer[0] != address or peer[1] != port:
                        continue
                    reply = decode_message(payload, token)
                    if (reply.get("kind") == "challenge"
                            and reply.get("session") == session
                            and reply.get("request") == request):
                        return
            except (socket.timeout, ValueError, UnicodeError, RecursionError):
                continue
    raise ValueError("The console did not accept the paired token; pair again from this Controller")


def pair_over_ssh(
    host: str,
    username: str,
    password: str,
    token: str,
    known_hosts: Path,
    platform: str,
    timeout: float = 30.0,
) -> None:
    """Install the token with an isolated Python SSH client and private stdin."""
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")
    if not host or len(host) > 253 or any(character.isspace() for character in host):
        raise ValueError("enter a valid console hostname or IP address")
    if not username or len(username) > 64 or any(character not in allowed for character in username):
        raise ValueError("enter a valid console username")
    if not password or "\n" in password or "\r" in password:
        raise ValueError("enter a valid console password")
    if not 16 <= len(token) <= 256:
        raise ValueError("invalid controller token")
    if platform not in CONSOLE_PLATFORMS:
        raise ValueError("choose a supported console platform")
    helper = Path(__file__).resolve().parents[2] / "python" / "ssh_pair.py"
    command = [
        "uv", "run", "--no-project", "--python", "3.12",
        "--with", "paramiko>=3.4,<5", "python", str(helper),
    ]
    # The web process does not inherit the vision worker's uv environment.
    # Persist pairing dependencies alongside that runtime across app restarts.
    environment = dict(os.environ)
    environment.pop("VIRTUAL_ENV", None)
    environment["PYTHONPATH"] = str(helper.parents[1] / "src")
    data_dir = helper.parents[1] / "data"
    environment["UV_CACHE_DIR"] = str(data_dir / "uv-cache")
    environment["UV_PYTHON_INSTALL_DIR"] = str(data_dir / "uv-python")
    try:
        prepared = subprocess.run(
            command[:-1] + ["-c", "import paramiko"],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            env=environment, timeout=120,
        )
    except subprocess.TimeoutExpired:
        raise ValueError("Preparing the SSH pairing runtime timed out; check UNO Q internet access and retry") from None
    if prepared.returncode:
        raise ValueError("Could not prepare the SSH pairing runtime; check UNO Q internet access and retry")
    # With dependencies prepared, do not spend the SSH deadline querying PyPI.
    command.insert(2, "--offline")
    payload = json.dumps({
        "host": host,
        "username": username,
        "password": password,
        "token": token,
        "known_hosts": str(known_hosts),
        "platform": platform,
        "timeout": timeout,
    }).encode()
    try:
        completed = subprocess.run(
            command,
            input=payload,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            timeout=timeout + 15,
            env=environment,
        )
    except subprocess.TimeoutExpired:
        raise ValueError("SSH pairing timed out connecting to or configuring the console; check its hostname and SSH access") from None
    finally:
        payload = b""
        password = ""
    if completed.returncode:
        error = completed.stderr.decode("utf-8", "replace").strip().splitlines()
        message = error[-1] if error else "SSH pairing failed"
        raise ValueError(message[:240])
    verify_controller_pairing(host, CONTROLLER_PORT, token)


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line parser for serving or initiating pairing."""
    parser = argparse.ArgumentParser(description="Pair VirtualGlove with a supported console")
    parser.add_argument("--listen", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=PAIRING_PORT)
    parser.add_argument("--token-file", type=Path, default=Path("/etc/virtualglove/token"))
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--receiver-service", default="virtualglove-receiver.service")
    parser.add_argument("--receiver-restart-command", nargs="+",
                        help="non-systemd console command used after pairing")
    return parser


def main() -> int:
    """Run the selected pairing role and return a process exit status."""
    args = build_parser().parse_args()

    def restart_receiver() -> None:
        """Restart the installed receiver after accepting a new shared token."""
        command = (args.receiver_restart_command or
                   ["systemctl", "restart", args.receiver_service])
        subprocess.run(command, check=True)

    try:
        serve_pairing(args.listen, args.port, args.token_file, args.timeout, restart_receiver)
        print("Pairing complete. VirtualGlove receiver restarted.", flush=True)
        return 0
    except TimeoutError as exc:
        print(str(exc), flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

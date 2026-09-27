"""Private Compose bridge from the portal app to its host user service."""
import json
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/request":
            self.send_error(404)
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if size < 1 or size > 512:
                raise ValueError("Invalid request size")
            message = json.loads(self.rfile.read(size))
            with socket.socket(socket.AF_UNIX) as conn:
                conn.settimeout(8)
                conn.connect("/broker/control.sock")
                conn.sendall((json.dumps(message) + "\n").encode())
                answer = bytearray()
                while not answer.endswith(b"\n") and len(answer) < 65536:
                    chunk = conn.recv(4096)
                    if not chunk:
                        break
                    answer.extend(chunk)
            result = json.loads(answer)
            body = json.dumps(result).encode()
            self.send_response(200)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            body = json.dumps({"error": str(exc)}).encode()
            self.send_response(503)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8122), Handler).serve_forever()

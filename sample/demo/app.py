"""Minimal demo app — shows Berth is working."""
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/health":
            body = json.dumps({"status": "healthy"}).encode()
            self.send_response(200)
        else:
            body = json.dumps({
                "message": "Hello from Berth! 🚀",
                "path": self.path,
                "host": self.headers.get("Host", ""),
                "served_by": "demo",
            }).encode()
            self.send_response(200)

        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"[demo] {fmt % args}")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print(f"Demo server listening on :{port}")
    HTTPServer(("0.0.0.0", port), Handler).serve_forever()

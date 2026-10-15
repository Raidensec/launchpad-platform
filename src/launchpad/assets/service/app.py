import argparse
import json
import os
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock

SERVICE_NAME = "{{SERVICE_NAME}}"


class ServiceHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address):
        super().__init__(address, ServiceRequestHandler)
        self.status_counts = Counter()
        self.metrics_lock = Lock()

    def record_status(self, status):
        with self.metrics_lock:
            self.status_counts[status] += 1


class ServiceRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/":
            self.send_json(200, {"service": SERVICE_NAME})
        elif self.path == "/healthz":
            self.send_json(200, {"status": "healthy"})
        elif self.path == "/readyz":
            self.send_json(200, {"status": "ready"})
        elif self.path == "/metrics":
            self.send_metrics()
        else:
            self.send_json(404, {"error": "not found"})

    def do_POST(self):
        self.send_json(405, {"error": "method not allowed"}, allow="GET")

    def send_json(self, status, payload, allow=None):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        if allow:
            self.send_header("Allow", allow)
        self.end_headers()
        self.server.record_status(status)
        self.wfile.write(body)

    def send_metrics(self):
        with self.server.metrics_lock:
            metrics = "".join(
                f'launchpad_http_requests_total{{status="{status}"}} {count}\n'
                for status, count in sorted(self.server.status_counts.items())
            )
        body = metrics.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.server.record_status(200)
        self.wfile.write(body)

    def log_message(self, format_string, *args):
        status = str(args[1]) if len(args) == 3 and str(args[1]).isdecimal() else "event"
        print(f"{self.log_date_time_string()} request_status={status}")


def parse_arguments():
    parser = argparse.ArgumentParser(prog=SERVICE_NAME)
    parser.add_argument("--host", default=os.getenv("HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "8000")))
    arguments = parser.parse_args()
    if not 0 <= arguments.port <= 65535:
        parser.error("--port must be between 0 and 65535")
    return arguments


def main():
    arguments = parse_arguments()
    server = ServiceHTTPServer((arguments.host, arguments.port))
    print(f"{SERVICE_NAME} listening on {arguments.host}:{server.server_port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()

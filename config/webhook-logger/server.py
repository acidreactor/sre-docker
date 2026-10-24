#!/usr/bin/env python3
"""Приёмник webhook-уведомлений Alertmanager.

Каждое уведомление пишется в stdout одной JSON-строкой — Alloy забирает её в Loki,
и история алертов видна в Grafana (дашборд «Логи», сервис webhook-logger).
GET / — последние 50 уведомлений в JSON (удобно проверить curl'ом).
"""
import json
from collections import deque
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LAST = deque(maxlen=50)


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)) or 0)
        try:
            payload = json.loads(body)
        except ValueError:
            self.send_response(400)
            self.end_headers()
            return
        for a in payload.get("alerts", []):
            event = {
                "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "status": a.get("status"),
                "alertname": a.get("labels", {}).get("alertname"),
                "severity": a.get("labels", {}).get("severity"),
                "instance": a.get("labels", {}).get("instance", ""),
                "summary": a.get("annotations", {}).get("summary", ""),
                "receiver": payload.get("receiver"),
            }
            LAST.append(event)
            print(json.dumps(event, ensure_ascii=False), flush=True)
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        data = json.dumps(list(LAST), ensure_ascii=False, indent=2).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 9000), Handler).serve_forever()

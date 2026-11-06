#!/usr/bin/env python3
"""Serve one immutable HTML snapshot on loopback, verify it, then print its URL."""
import argparse
from datetime import datetime, timedelta, timezone
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import secrets
import threading

from delivery import artifact_path


def make_server(path, port=0):
    path = artifact_path(path)
    payload = path.read_bytes()
    route = '/' + secrets.token_urlsafe(18) + '/explanation.html'

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.respond(False)

        def do_HEAD(self):
            self.respond(True)

        def respond(self, head):
            if self.path != route:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(payload)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.end_headers()
            if not head:
                self.wfile.write(payload)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    return server, route, payload


def verify(server, route, payload):
    connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
    try:
        connection.request('GET', route)
        response = connection.getresponse()
        if response.status != 200 or response.read() != payload:
            raise ValueError('Local preview verification failed')
    finally:
        connection.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('html')
    parser.add_argument('--port', type=int, default=0)
    parser.add_argument('--lifetime-seconds', type=int, default=7200)
    args = parser.parse_args()
    if not 0 <= args.port <= 65535 or not 1 <= args.lifetime_seconds <= 86400:
        parser.error('port must be 0..65535 and lifetime-seconds 1..86400')
    if os.environ.get('SSH_CONNECTION') or os.environ.get('SSH_TTY'):
        parser.error('SSH session: deliver the artifact to the reader computer before starting local preview')
    try:
        path = artifact_path(args.html)
        server, route, payload = make_server(path, args.port)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            verify(server, route, payload)
            url = f'http://127.0.0.1:{server.server_port}{route}'
            expires = datetime.now(timezone.utc) + timedelta(seconds=args.lifetime_seconds)
            print(json.dumps({'preview_url': url, 'browser_link': f'[Открыть объяснение и quiz]({url})',
                              'file_path': str(path), 'verified_http': True,
                              'expires_at': expires.isoformat(), 'lifetime_seconds': args.lifetime_seconds}, ensure_ascii=False), flush=True)
            worker.join(args.lifetime_seconds)
        finally:
            server.shutdown()
            server.server_close()
            worker.join()
    except KeyboardInterrupt:
        pass
    except (OSError, ValueError, http.client.HTTPException) as exc:
        parser.exit(2, f'Preview error: {exc}\n')


if __name__ == '__main__':
    main()

"""Real loopback tests; requires permission to bind/connect to 127.0.0.1."""
import http.client
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from urllib.parse import urlsplit

SCRIPTS = Path(__file__).resolve().parents[1] / 'skills/understand-changes/scripts'
sys.path.insert(0, str(SCRIPTS))
import preview


class PreviewTests(unittest.TestCase):
    def test_only_artifact_is_served_with_html_content_type(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'explanation.html'
            payload = b'<!doctype html><title>Quiz</title>'
            path.write_bytes(payload)
            (Path(tmp) / 'private.txt').write_text('not exposed')
            server, route, expected = preview.make_server(path)
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                self.assertEqual(server.server_address[0], '127.0.0.1')
                preview.verify(server, route, expected)
                for target, status in ((route, 200), ('/', 404), ('/private.txt', 404), (route + '/../../private.txt', 404)):
                    connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=2)
                    connection.request('GET', target)
                    response = connection.getresponse()
                    body = response.read()
                    self.assertEqual(response.status, status)
                    if status == 200:
                        self.assertEqual(body, payload)
                        self.assertEqual(response.getheader('Content-Type'), 'text/html; charset=utf-8')
                    else:
                        self.assertNotIn(b'not exposed', body)
                    connection.close()
            finally:
                server.shutdown()
                server.server_close()
                worker.join()

    def test_served_snapshot_does_not_change_after_file_edit(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'explanation.html'
            path.write_bytes(b'original')
            server, route, payload = preview.make_server(path)
            path.write_bytes(b'modified')
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                preview.verify(server, route, b'original')
            finally:
                server.shutdown()
                server.server_close()
                worker.join()

    def test_cli_announces_verified_url_and_exits_after_lifetime(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'explanation.html'
            path.write_bytes(b'<!doctype html><title>Quiz</title>')
            env = {k: v for k, v in os.environ.items() if k not in ('SSH_CONNECTION', 'SSH_TTY')}
            process = subprocess.Popen([sys.executable, str(SCRIPTS / 'preview.py'), str(path), '--lifetime-seconds', '1'], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                stdout, stderr = process.communicate(timeout=5)
                self.assertEqual(process.returncode, 0, stderr)
                result = json.loads(stdout)
                self.assertTrue(result['verified_http'])
                self.assertEqual(result['lifetime_seconds'], 1)
                url = urlsplit(result['preview_url'])
                connection = http.client.HTTPConnection(url.hostname, url.port, timeout=1)
                with self.assertRaises(OSError):
                    connection.request('GET', url.path)
                connection.close()
            finally:
                if process.poll() is None:
                    process.kill()
                    process.communicate()


if __name__ == '__main__':
    unittest.main()

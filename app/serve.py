"""Serve the CityPulse website and power its "Update now" button.

Run:  python -I -X utf8 app/serve.py [--port 8790]
Then open http://127.0.0.1:8790/

Without this helper the page still works: open app/index.html directly (file://). It then shows the
last stored receipt, and "Replay the last check" works; "Update now" needs this server.

Endpoints
  GET  /api/status                 {"ok": true, "busy": bool}
  POST /api/update?mode=quick      runs live/update_now.py --quick and streams its output line by line
  POST /api/update?mode=offline    runs live/update_now.py --no-collect (no network scan, reuses the last scan)
  POST /api/ask {q, last}          Ask CityPulse: a language model reads the question into a checked query (app/ask_model.py)
After a run it rebuilds app/data/ (app/build_data.py) and ends with a line "CITYPULSE_DONE <exit code>".
Only one run at a time. Nothing under live/ or pipeline/ is edited by this file; update_now.py writes its
own receipts in live/out/update/ as it does when run from UPDATE_NOW.cmd.
Standard library only.
"""
import os, sys, json, argparse, threading, subprocess, http.server, socketserver, functools
from urllib.parse import urlparse, parse_qs

APP = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(APP)
sys.path.insert(0, APP)
import ask_model   # noqa: E402  (Ask CityPulse question reader; standard library only)
UPDATE = os.environ.get('CITYPULSE_UPDATE_SCRIPT') or os.path.join(ROOT, 'live', 'update_now.py')   # override only for tests
BUILD = os.path.join(APP, 'build_data.py')
MODES = {'quick': ['--quick'], 'offline': ['--no-collect']}
LOCK = threading.Lock()


class H(http.server.SimpleHTTPRequestHandler):
    protocol_version = 'HTTP/1.0'   # the stream ends when the connection closes

    def _json(self, code, obj):
        body = json.dumps(obj).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith('/api/status'):
            return self._json(200, {'ok': True, 'busy': LOCK.locked(), 'update_script': os.path.exists(UPDATE), 'ask_model': ask_model.status()})
        if self.path.startswith('/api/'):
            return self._json(404, {'ok': False})
        if 'If-Modified-Since' in self.headers:
            del self.headers['If-Modified-Since']   # always send the current file (no stale data on stage)
        return super().do_GET()

    def do_POST(self):
        u = urlparse(self.path)
        if u.path == '/api/ask':   # Ask CityPulse: the model reads the question into a query (app/ask_model.py); answers are computed in the page
            try:
                n = min(int(self.headers.get('Content-Length') or 0), 4000)
                req = json.loads(self.rfile.read(n) or b'{}')
            except Exception:
                return self._json(400, {'ok': False, 'error': 'bad request'})
            return self._json(200, ask_model.read(req.get('q'), req.get('last')))
        if u.path != '/api/update':
            return self._json(404, {'ok': False})
        mode = (parse_qs(u.query).get('mode') or ['quick'])[0]
        if mode not in MODES:
            return self._json(400, {'ok': False, 'error': 'mode must be quick or offline'})
        if not LOCK.acquire(blocking=False):
            return self._json(409, {'ok': False, 'error': 'a check is already running'})
        try:
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Accel-Buffering', 'no')
            self.end_headers()
            code = self._stream([sys.executable, '-I', '-X', 'utf8', '-u', UPDATE] + MODES[mode])
            if code == 0:
                self._stream([sys.executable, '-I', '-X', 'utf8', BUILD])
            self._line(f'CITYPULSE_DONE {code}')
        except (BrokenPipeError, ConnectionResetError):
            pass   # the browser left; the run itself finished or was stopped above
        finally:
            LOCK.release()

    def _line(self, s):
        self.wfile.write((s.rstrip('\n') + '\n').encode('utf-8'))
        self.wfile.flush()

    def _stream(self, cmd):
        env = dict(os.environ, PYTHONIOENCODING='utf-8')
        p = subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env,
                             text=True, encoding='utf-8', errors='replace', bufsize=1)
        try:
            for line in p.stdout:
                self._line(line)
        except (BrokenPipeError, ConnectionResetError):
            p.wait()
            raise
        return p.wait()

    def end_headers(self):
        if not self.path.startswith('/api/'):
            self.send_header('Cache-Control', 'no-store')
        super().end_headers()

    def log_message(self, *a):
        pass


class Server(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', type=int, default=int(os.environ.get('PORT', 8790)))
    a = ap.parse_args()
    with Server(('127.0.0.1', a.port), functools.partial(H, directory=APP)) as s:
        print(f'CityPulse on http://127.0.0.1:{a.port}/  (Ctrl+C to stop)', flush=True)
        s.serve_forever()

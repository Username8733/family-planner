"""Ingress authentication, CSRF and prefixed API routes using local HTTP fixtures."""
import importlib.util
import json
import tempfile
import threading
import urllib.error
import urllib.request
from functools import partial
from pathlib import Path
from serve import CalendarHTTPServer
from online_calendar import ICloudCalendar

root = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("ha_ingress", root / "home-assistant/addon/run.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class TrustedPeer(module.IngressHandler):
    def setup(self):
        super().setup()
        self.client_address = ("172.30.32.2", self.client_address[1])

def request(server, path, data=None, headers=None):
    values = {"Host": "ha.example.test", "X-Ingress-Path": "/api/hassio_ingress/fixture", **(headers or {})}
    if data is not None:
        values["Content-Type"] = "application/json"
    req = urllib.request.Request("http://127.0.0.1:" + str(server.server_port) + path,
                                 None if data is None else json.dumps(data).encode(), headers=values)
    try:
        response = urllib.request.urlopen(req)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        raw = response.read()
        try:
            body = json.loads(raw)
        except ValueError:
            body = None
        return response.status, body

with tempfile.TemporaryDirectory() as folder:
    for trusted in [False, True]:
        server = CalendarHTTPServer(("127.0.0.1", 0), root / "dist",
                                    ICloudCalendar(Path(folder) / "icloud.json"), behind_proxy=True)
        handler = TrustedPeer if trusted else module.IngressHandler
        server.RequestHandlerClass = partial(handler, directory=str(root / "dist"))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            status, session = request(server, "/api/session")
            if not trusted:
                assert status == 403
                assert request(server, "/api/oauth/google/callback?state=invalid")[0] == 403
                continue
            assert status == 200 and session["ready"]
            assert request(server, "/api/session", headers={"X-Ingress-Path": "/wrong"})[0] == 403
            assert request(server, "/api/v2/sources", {})[0] == 403
            csrf = {"X-Hemma-CSRF": session["csrf"]}
            assert request(server, "/api/v2/sources", {}, {**csrf, "Origin": "https://untrusted.example"})[0] == 403
            server.sources.add = lambda body, callback: {"callback": callback}
            status, result = request(server, "/api/v2/sources", {}, {**csrf, "Origin": "https://ha.example.test"})
            assert status == 200
            assert result["callback"] == "https://ha.example.test/api/hassio_ingress/fixture/api/oauth/google/callback"
            server.dashboard_callback_path = "/dashboard-family-planner/calendar"
            status, result = request(server, "/api/v2/sources", {}, {**csrf, "Origin": "https://ha.example.test"})
            assert status == 200 and result["callback"] == "https://ha.example.test/dashboard-family-planner/calendar"
            assert request(server, "/icloud.json")[0] == 404
        finally:
            server.shutdown()
            server.server_close()
            thread.join(5)
print("PASS: ingress rejects direct access and malformed prefixes; authenticated session, CSRF/origin checks, prefixed OAuth redirect and private-file isolation.")

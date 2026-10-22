"""HA-only entry point. Supervisor ingress authenticates every browser request."""
import json
import os
import re
from functools import partial
from pathlib import Path
from urllib.parse import urlsplit
from serve import CalendarHTTPServer, Handler
from online_calendar import ICloudCalendar

class IngressHandler(Handler):
    def _ingress_request(self):
        # Headers only become trustworthy after checking the actual TCP peer.
        if self.client_address[0] != "172.30.32.2":
            self._json({"error": "Home Assistant ingress is required."}, 403)
            return False
        prefix = self.headers.get("X-Ingress-Path", "")
        try:
            host = urlsplit("//" + self.headers.get("Host", "")).hostname
            if not host or not re.fullmatch(r"/api/hassio_ingress/[A-Za-z0-9_-]+", prefix.rstrip("/")):
                raise ValueError()
        except ValueError:
            self._json({"error": "Invalid ingress request."}, 403)
            return False
        self.server.allowed_hosts.add(host)
        return True

    def _authorized(self, mutate=False):
        return self._ingress_request() and super()._authorized(mutate)

    def do_GET(self):
        # The OAuth callback skips ordinary CSRF checks, but never ingress auth.
        if self._ingress_request():
            super().do_GET()

    def _google_callback_url(self):
        prefix = self.headers["X-Ingress-Path"].rstrip("/")
        # Return through the HA frontend, which establishes an ingress session
        # before the card forwards Google's one-time code to the protected API.
        return "https://" + self.headers["Host"] + getattr(
            self.server, "dashboard_callback_path", prefix + "/api/oauth/google/callback")

if __name__ == "__main__":
    os.umask(0o077)
    backend = ICloudCalendar(Path("/data/icloud.json"))
    server = CalendarHTTPServer(("0.0.0.0", 8099), Path(__file__).parent / "dist",
                                backend=backend, behind_proxy=True)
    options = json.loads(Path("/data/options.json").read_text())
    callback = options.get("dashboard_path", "/dashboard-family-planner/calendar")
    if not re.fullmatch(r"/[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*", callback):
        raise ValueError("dashboard_path must be a local dashboard path without a query.")
    server.dashboard_callback_path = callback
    server.RequestHandlerClass = partial(IngressHandler, directory=str(Path(__file__).parent / "dist"))
    print("Family Planner is ready through Home Assistant ingress.", flush=True)
    server.serve_forever()

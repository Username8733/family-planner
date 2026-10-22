
"""Standalone static app and same-origin iCloud API. Credentials stay on the server."""
import argparse
import base64
import hmac
import importlib.util
import json
import os
import secrets
import ssl
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from online_calendar import ICloudCalendar, CalendarError
from calendar_sources import CalendarSources

class CalendarHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    def __init__(self, address, directory, backend=None, public_host=None, basic_auth=None, behind_proxy=False):
        self.backend = backend or ICloudCalendar()
        self.sources = CalendarSources(self.backend)
        self.csrf = secrets.token_urlsafe(32)
        self.allowed_hosts = {'localhost','127.0.0.1','::1'}
        if public_host:
            self.allowed_hosts.add(public_host.lower())
        self.basic_auth = basic_auth
        self.behind_proxy = behind_proxy
        super().__init__(address, partial(Handler, directory=str(directory)))

class Handler(SimpleHTTPRequestHandler):
    def log_request(self, code="-", size="-"):
        if urlsplit(self.path).path == "/api/oauth/google/callback":
            self.log_message("Google OAuth callback %s", code)
        else:
            super().log_request(code, size)

    def end_headers(self):
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'same-origin')
        super().end_headers()

    def _json(self, value, status=200):
        body = json.dumps(value, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self, mutate=False):
        try:
            host = urlsplit('//'+self.headers.get('Host','')).hostname
            if host not in self.server.allowed_hosts:
                self._json({'error':'Invalid host address.'},403)
                return False
            if self.server.basic_auth:
                expected = 'Basic '+base64.b64encode(':'.join(self.server.basic_auth).encode()).decode()
                if not hmac.compare_digest(self.headers.get('Authorization',''), expected):
                    self.send_response(401)
                    self.send_header('WWW-Authenticate','Basic realm="Family Planner", charset="UTF-8"')
                    self.end_headers()
                    return False
            if self.headers.get('Sec-Fetch-Site') == 'cross-site':
                self._json({'error':'The request comes from another website.'},403)
                return False
            if mutate:
                origin = self.headers.get('Origin')
                if origin and urlsplit(origin).netloc.lower() != self.headers.get('Host','').lower():
                    self._json({'error':'Invalid origin.'},403)
                    return False
                if not hmac.compare_digest(self.headers.get('X-Hemma-CSRF',''),self.server.csrf):
                    self._json({'error':'Reload the page and try again.'},403)
                    return False
            return True
        except ValueError:
            self._json({'error':'Invalid request.'},400)
            return False

    def _body(self):
        size = int(self.headers.get('Content-Length','0'))
        if not 0 < size <= 65536 or self.headers.get_content_type() != 'application/json':
            raise CalendarError('Send a valid JSON request.',400)
        result = json.loads(self.rfile.read(size))
        if not isinstance(result,dict):
            raise CalendarError('Invalid data.')
        return result

    def _google_callback_url(self):
        scheme = 'https' if isinstance(self.connection, ssl.SSLSocket) or self.server.behind_proxy else 'http'
        return scheme+'://'+self.headers['Host']+'/api/oauth/google/callback'

    def _api(self):
        if not self._authorized(self.command != 'GET'):
            return
        try:
            path = urlsplit(self.path).path
            backend = self.server.backend
            if path == '/api/v2/sources':
                if self.command == 'GET':
                    result = self.server.sources.list()
                elif self.command == 'POST':
                    result = self.server.sources.add(self._body(), self._google_callback_url())
                else:
                    raise CalendarError('The API endpoint does not exist.',404)
            elif path.startswith('/api/v2/sources/'):
                sid = path.rsplit('/',1)[-1]
                if self.command == 'PUT':
                    result = self.server.sources.configure(sid,self._body())
                elif self.command == 'DELETE':
                    result = self.server.sources.remove(sid)
                else:
                    raise CalendarError('The API endpoint does not exist.',404)
            elif path == '/api/v2/events':
                if self.command == 'GET':
                    query = parse_qs(urlsplit(self.path).query)
                    result = self.server.sources.events(query.get('start',[''])[0],query.get('end',[''])[0])
                elif self.command in ['POST','PUT','DELETE']:
                    result = self.server.sources.mutate(self.command,self._body())
                else:
                    raise CalendarError('The API endpoint does not exist.',404)
            elif self.command == 'GET' and path == '/api/session':
                ready = all(importlib.util.find_spec(name) for name in ['caldav','icalendar','recurring_ical_events'])
                result = {'csrf':self.server.csrf, 'ready':ready, **backend.status()}
            elif self.command == 'GET' and path == '/api/calendars':
                result = backend.calendars()
            elif self.command == 'GET' and path == '/api/events':
                query = parse_qs(urlsplit(self.path).query)
                result = backend.events(query.get('start',[''])[0],query.get('end',[''])[0])
            elif self.command == 'POST' and path == '/api/connection':
                body = self._body()
                result = backend.connect(body.get('username'),body.get('password'))
            elif self.command == 'DELETE' and path == '/api/connection':
                result = backend.disconnect()
            elif self.command == 'POST' and path == '/api/selection':
                body = self._body()
                result = backend.select(body.get('calendarId'),body.get('timezone','Europe/Stockholm'))
            elif self.command in ['POST','PUT','DELETE'] and path == '/api/events':
                body = self._body()
                if self.command == 'POST':
                    result = backend.create(body)
                elif self.command == 'PUT':
                    result = backend.update(body.get('id',''),body.get('etag',''),body)
                else:
                    result = backend.delete(body.get('id',''),body.get('etag',''))
            else:
                raise CalendarError('The API endpoint does not exist.',404)
            self._json(result)
        except CalendarError as error:
            self._json({'error':str(error)},error.status)
        except (ValueError,TypeError,KeyError,json.JSONDecodeError):
            self._json({'error':'The data could not be parsed. Check the form.'},400)
        except Exception as error:
            # Never return/log upstream exception text: it can include sensitive URLs.
            name = type(error).__name__
            message = ('iCloud denied login. Check your Apple ID and app-specific password.'
                       if 'Authoriz' in name or 'Authentic' in name
                       else 'The calendar service could not be reached or denied the operation. Check its connection and permissions.')
            self._json({'error':message},502)

    def do_GET(self):
        if urlsplit(self.path).path == '/api/oauth/google/callback':
            # Google navigates cross-site to this endpoint. Only the one-use,
            # short-lived PKCE state issued by our CSRF-protected POST is accepted.
            try:
                host = urlsplit('//'+self.headers.get('Host','')).hostname
                if host not in self.server.allowed_hosts:
                    raise CalendarError('Invalid host address.',403)
                query = parse_qs(urlsplit(self.path).query)
                self.server.sources.google_callback(query.get('state',[''])[0],query.get('code',[''])[0])
                message = 'Google connected. Close this tab and choose calendars in Settings.'
                status = 200
            except Exception:
                message = 'Google could not be connected. Try again from Settings.'
                status = 400
            body = ('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Family Planner</title><body style="font:18px system-ui;padding:32px;max-width:640px"><p>'+message+'</p></body></html>').encode()
            self.send_response(status);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
            return
        if urlsplit(self.path).path.startswith('/api/'):
            return self._api()
        if self._authorized():
            super().do_GET()

    def do_HEAD(self):
        if self._authorized():
            super().do_HEAD()

    def do_POST(self):
        self._api()
    def do_PUT(self):
        self._api()
    def do_DELETE(self):
        self._api()

    def list_directory(self, path):
        self.send_error(404)
        return None

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Family Planner with online calendars')
    parser.add_argument('--host',default='127.0.0.1')
    parser.add_argument('--port',type=int,default=8086)
    parser.add_argument('--public-host',help='Hostname in the HTTPS address, without a scheme or port.')
    parser.add_argument('--behind-https-proxy',action='store_true')
    parser.add_argument('--tls-cert')
    parser.add_argument('--tls-key')
    parser.add_argument('--credentials-file',type=Path)
    args = parser.parse_args()
    username,password = os.environ.get('HEMMA_HTTP_USERNAME'),os.environ.get('HEMMA_HTTP_PASSWORD')
    auth = (username,password) if username and password else None
    if args.host not in ['127.0.0.1','localhost','::1']:
        if not auth or not (args.tls_cert and args.tls_key or args.behind_https_proxy):
            parser.error('Network access requires HEMMA_HTTP_USERNAME/HEMMA_HTTP_PASSWORD and TLS or --behind-https-proxy. Use localhost for local access.')
    if args.credentials_file and args.credentials_file.resolve().is_relative_to(Path(__file__).resolve().parent/'dist'):
        parser.error('The credentials file must be outside the dist directory.')
    backend = ICloudCalendar(args.credentials_file)
    server = CalendarHTTPServer((args.host,args.port),Path(__file__).resolve().parent/'dist',
                                backend,args.public_host,auth,args.behind_https_proxy)
    scheme = 'http'
    if args.tls_cert and args.tls_key:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(args.tls_cert,args.tls_key)
        server.socket = context.wrap_socket(server.socket,server_side=True)
        scheme = 'https'
    print(f'Family Planner: {scheme}://{args.host}:{server.server_port}/',flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

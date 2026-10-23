
"""iCloud CalDAV transport. No credentials or calendar content is served as static files."""
import base64
import copy
import hashlib
import hmac
import json
import os
import secrets
import tempfile
import threading
import uuid
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from zoneinfo import ZoneInfo

class CalendarError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status

DETAIL_LIMITS = {"description":10000, "location":1000}

def event_details(item, existing=None):
    result={}
    for field,limit in DETAIL_LIMITS.items():
        if field not in item:
            continue
        value=item[field]
        if not isinstance(value,str) or len(value)>limit and value!=(existing or {}).get(field):
            raise CalendarError("Notes may contain up to 10000 characters and location up to 1000 characters.",400)
        result[field]=value
    return result

def libraries():
    try:
        import caldav
        import icalendar
        import recurring_ical_events
        return caldav, icalendar, recurring_ical_events
    except ImportError:
        raise CalendarError('Install the calendar libraries as described in ONLINE-CALENDAR.md.', 503)

def date_value(value):
    return value.dt if hasattr(value, 'dt') else value

def identity(value):
    value = date_value(value)
    if isinstance(value, datetime):
        if value.tzinfo:
            value = value.astimezone(timezone.utc)
        return 'T:' + value.isoformat()
    return 'D:' + value.isoformat()

def parse_identity(value):
    kind, raw = value.split(':', 1)
    return date.fromisoformat(raw) if kind == 'D' else datetime.fromisoformat(raw)

def get_end(component):
    start = component.decoded('DTSTART')
    if component.get('DTEND') is not None:
        return component.decoded('DTEND')
    duration = component.get('DURATION')
    if duration is not None:
        return start + component.decoded('DURATION')
    return start + (timedelta() if isinstance(start, datetime) else timedelta(days=1))

class ICloudCalendar:
    def __init__(self, config_file=None, server_url='https://caldav.icloud.com/'):
        self.config_file = Path(config_file or Path.home()/'.local/share/hemma-calendar/icloud.json')
        self.server_url = server_url  # Only the test harness supplies a non-Apple URL.
        self.lock = threading.RLock()
        self.config = {}
        if self.config_file.exists():
            self.config = json.loads(self.config_file.read_text())
        self.sign_key = self.config.get('sign_key') or secrets.token_hex(32)
        self.calendar_cache = {}

    def _write_config(self, config):
        config = dict(config, sign_key=self.sign_key)
        self.config_file.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd, filename = tempfile.mkstemp(prefix='.icloud-', dir=self.config_file.parent)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, 'w') as handle:
                json.dump(config, handle)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(filename, self.config_file)
        finally:
            if os.path.exists(filename):
                os.unlink(filename)
        self.config = config

    def status(self):
        return {'configured': bool(self.config.get('username')), 'appleId':self.config.get('username',''),
                'calendarId': self.config.get('calendar_id', ''),
                'calendarName': self.config.get('calendar_name', ''),
                'timezone': self.config.get('timezone', 'Europe/Stockholm')}

    def _client(self, config=None, selected=False):
        caldav, _, _ = libraries()
        config = config or self.config
        if not config.get('username'):
            raise CalendarError('Connect an iCloud account in Settings.', 409)
        # iCloud discovery can return a calendar on a different shard hostname.
        # Calendar objects must use that discovered base, since caldav rejects
        # joining absolute URLs across hosts. Keep discovery on the entry point.
        base_url = self._selected() if selected else self.server_url
        return caldav.DAVClient(url=base_url, username=config['username'],
                                password=config['password'], timeout=20,
                                require_tls=self.server_url.startswith('https:'),
                                enable_rfc6764=False)

    def _discover(self, config=None):
        with self._client(config) as client:
            calendars = client.get_principal().get_calendars()
            found = {}
            for calendar in calendars:
                url = str(calendar.url)
                calendar_id = hashlib.sha256(url.encode()).hexdigest()[:24]
                found[calendar_id] = {'id':calendar_id, 'name':calendar.get_display_name() or 'Kalender',
                                      'url':url}
            return found

    def connect(self, username, password):
        if not isinstance(username, str) or '@' not in username or not isinstance(password, str) or len(password.strip()) < 12:
            raise CalendarError('Enter your Apple ID and an app-specific password.')
        candidate = {'username':username.strip(), 'password':password.strip(),
                     'timezone':self.config.get('timezone', 'Europe/Stockholm')}
        with self.lock:
            found = self._discover(candidate)  # Existing connection is retained on failure.
            self._write_config(candidate)
            self.calendar_cache = found
            return self.calendars(cached=True)

    def disconnect(self):
        with self.lock:
            self._write_config({})
            self.calendar_cache = {}
        return self.status()

    def calendars(self, cached=False):
        with self.lock:
            if not cached or not self.calendar_cache:
                self.calendar_cache = self._discover()
            return {'calendars':[{'id':v['id'], 'name':v['name']} for v in self.calendar_cache.values()],
                    **self.status()}

    def select(self, calendar_id, tz_name='Europe/Stockholm'):
        try:
            ZoneInfo(tz_name)
        except (ValueError, KeyError):
            raise CalendarError('Choose a valid IANA time zone, for example Europe/Stockholm.')
        with self.lock:
            if not self.calendar_cache:
                self.calendar_cache = self._discover()
            chosen = self.calendar_cache.get(calendar_id)
            if not chosen:
                raise CalendarError("The calendar is not in the account's calendar list.", 404)
            self._write_config(dict(self.config, calendar_id=calendar_id,
                                    calendar_name=chosen['name'], calendar_url=chosen['url'], timezone=tz_name))
        return self.status()

    def _selected(self):
        if not self.config.get('calendar_url'):
            raise CalendarError('Choose which iCloud calendar to use.', 409)
        return self.config['calendar_url']

    def _token(self, data):
        encoded = base64.urlsafe_b64encode(json.dumps(data, separators=(',', ':')).encode()).decode().rstrip('=')
        signature = hmac.new(self.sign_key.encode(), encoded.encode(), hashlib.sha256).hexdigest()
        return encoded + '.' + signature

    def _decode(self, token):
        try:
            encoded, signature = token.rsplit('.', 1)
            expected = hmac.new(self.sign_key.encode(), encoded.encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(expected, signature):
                raise ValueError()
            data = json.loads(base64.urlsafe_b64decode(encoded + '='*(-len(encoded)%4)))
            calendar = self._selected()
            target, base = urlsplit(data['url']), urlsplit(calendar)
            if (target.scheme, target.netloc) != (base.scheme, base.netloc) or not target.path.startswith(base.path.rstrip('/')+'/') or target.query or target.fragment or data['calendar'] != self.config['calendar_id']:
                raise ValueError()
            return data
        except (ValueError, KeyError, TypeError):
            raise CalendarError('The event reference is not valid for the selected calendar.', 400)

    def _fetch(self, client, url):
        _, icalendar, _ = libraries()
        response = client.request(url, method='GET')
        if response.status == 404:
            raise CalendarError('The event has been deleted in iCloud. Refresh the calendar.', 409)
        if response.status != 200:
            raise CalendarError('Could not read the calendar event.', 502)
        if len(response.raw) > 2_000_000:
            raise CalendarError('The calendar event is too large.', 422)
        return icalendar.Calendar.from_ical(response.raw), response.headers.get('ETag') or response.headers.get('etag')

    def _serialize(self, component, root, url, etag):
        tz = ZoneInfo(self.config.get('timezone', 'Europe/Stockholm'))
        start, end = component.decoded('DTSTART'), get_end(component)
        uid = str(component.get('UID', ''))
        originals = [c for c in root.walk('VEVENT') if str(c.get('UID', '')) == uid]
        recurring = any(c.get('RRULE') is not None or c.get('RDATE') is not None or c.get('RECURRENCE-ID') is not None for c in originals)
        recurrence = component.get('RECURRENCE-ID')
        rid = identity(recurrence or start) if recurring else None
        timed = isinstance(start, datetime)
        if timed:
            start = start.replace(tzinfo=start.tzinfo or tz).astimezone(tz)
            if not isinstance(end, datetime):
                raise CalendarError('The event mixes date and date-time values.', 422)
            end = end.replace(tzinfo=end.tzinfo or tz).astimezone(tz)
            display_end = end.date() - timedelta(days=1) if end.time().replace(tzinfo=None) == time() and end > start else end.date()
            end_day, end_time = end.date().isoformat(), end.strftime('%H:%M')
            data = {'date':start.date().isoformat(), 'endDate':max(start.date(), display_end).isoformat(),
                    'time':start.strftime('%H:%M'), 'end':end_time if display_end == end.date() else '',
                    'editEndDate':end_day, 'editEndTime':end_time, 'allDay':False}
        else:
            last = max(start, end-timedelta(days=1))
            data = {'date':start.isoformat(), 'endDate':last.isoformat(), 'time':'', 'end':'',
                    'editEndDate':last.isoformat(), 'editEndTime':'', 'allDay':True}
        return dict(data, id=self._token({'url':url, 'uid':uid, 'rid':rid, 'calendar':self.config['calendar_id']}),
                    summary=str(component.get('SUMMARY', '(Untitled)')),
                    description=str(component.get('DESCRIPTION','')),location=str(component.get('LOCATION','')),
                    etag=etag, recurring=recurring, calendarName=self.config.get('calendar_name', 'iCloud'),
                    writable=bool(etag))

    def events(self, start_text, end_text):
        try:
            first, last = date.fromisoformat(start_text), date.fromisoformat(end_text)
            if first.year < 2000 or last.year > 2101 or not 0 < (last-first).days <= 95:
                raise ValueError()
        except (ValueError, TypeError):
            raise CalendarError('Enter a valid date range of up to 95 days.')
        with self.lock:
            caldav, _, recurring = libraries()
            tz = ZoneInfo(self.config.get('timezone', 'Europe/Stockholm'))
            start, end = datetime.combine(first, time(), tz), datetime.combine(last, time(), tz)
            output, seen = [], set()
            with self._client(selected=True) as client:
                calendar = caldav.Calendar(client=client, url=self._selected())
                for obj in calendar.search(start=start, end=end, event=True, expand=False):
                    url = str(obj.url)
                    if url in seen:
                        continue
                    seen.add(url)
                    # Validate URLs supplied by the server before authenticated GET.
                    token = self._token({'url':url, 'uid':'', 'rid':None, 'calendar':self.config['calendar_id']})
                    self._decode(token)
                    original, etag = self._fetch(client, url)
                    for component in recurring.of(original).between(start, end):
                        if str(component.get('STATUS', '')).upper() == 'CANCELLED':
                            continue
                        output.append(self._serialize(component, original, url, etag))
                        if len(output) > 2500:
                            raise CalendarError('Too many events in the range. Select fewer calendars or a shorter range.', 422)
            unique = {event['id']:event for event in output}
            return {'events':list(unique.values()), 'timezone':str(tz), **self.status()}

    def _dates(self, item, existing=None):
        try:
            first = date.fromisoformat(item['date'])
            last = date.fromisoformat(item['endDate'])
            if not 2000 <= first.year <= 2100 or last < first or last.year > 2100:
                raise ValueError()
            start_time, end_time = item.get('time', ''), item.get('end', '')
            if not start_time and not end_time:
                return first, last+timedelta(days=1)
            if not start_time or not end_time or len(start_time) != 5 or len(end_time) != 5:
                raise ValueError()
            tz = ZoneInfo(self.config.get('timezone', 'Europe/Stockholm'))
            start = datetime.combine(first, time.fromisoformat(start_time), tz)
            end = datetime.combine(last, time.fromisoformat(end_time), tz)
            # Preserve an existing event's chosen offset in the repeated autumn hour.
            if existing is not None:
                old_start, old_end = existing.decoded('DTSTART'), get_end(existing)
                points = []
                for point, old in [(start, old_start), (end, old_end)]:
                    if isinstance(old, datetime) and old.tzinfo:
                        local = old.astimezone(tz)
                        if local.replace(tzinfo=None) == point.replace(tzinfo=None):
                            point = point.replace(fold=local.fold)
                    points.append(point)
                start, end = points
            for point in [start, end]:
                if point.astimezone(timezone.utc).astimezone(tz).replace(tzinfo=None) != point.replace(tzinfo=None):
                    raise CalendarError('This time does not exist because of the daylight-saving change. Choose another time.')
            if end.astimezone(timezone.utc) <= start.astimezone(timezone.utc):
                raise ValueError()
            return start, end
        except (ValueError, KeyError, TypeError):
            raise CalendarError('Check the dates and times. Enter both start and end times, or leave both blank for all day.')

    def _apply(self, component, item):
        summary = item.get('summary', '')
        if not isinstance(summary, str) or not summary.strip() or len(summary) > 512:
            raise CalendarError('The event title must contain 1–512 characters.')
        details=event_details(item, {"description":str(component.get("DESCRIPTION","")),"location":str(component.get("LOCATION",""))})
        for field,value in details.items():
            name=field.upper()
            if value==str(component.get(name,"")):
                continue
            component.pop(name,None)
            if value: component.add(name,value)
        start, end = self._dates(item, component if component.get("DTSTART") is not None else None)
        if isinstance(start, datetime):
            # UTC serialization unambiguously retains the second autumn hour.
            start, end = start.astimezone(timezone.utc), end.astimezone(timezone.utc)
        for key, value in [('SUMMARY', summary.strip()), ('DTSTART', start), ('DTEND', end),
                           ('DTSTAMP', datetime.now(timezone.utc)), ('LAST-MODIFIED', datetime.now(timezone.utc))]:
            component.pop(key, None)
            component.add(key, value)
        component.pop('DURATION', None)
        sequence = int(component.get('SEQUENCE', 0)) + 1
        component.pop('SEQUENCE', None)
        component.add('SEQUENCE', sequence)
        return component

    def _put(self, client, url, root, etag=None, create=False):
        headers = {'Content-Type':'text/calendar; charset=utf-8'}
        if create:
            headers['If-None-Match'] = '*'
        elif etag:
            headers['If-Match'] = etag
        else:
            raise CalendarError('The server provides no version information. The event will not be changed.', 409)
        response = client.put(url, root.to_ical(), headers=headers)
        if response.status in (409, 412):
            raise CalendarError('The event has changed in iCloud. Refresh and reopen it before saving.', 409)
        if response.status not in (200, 201, 204):
            raise CalendarError('The calendar rejected the change. Check its permissions.', 502)

    def create(self, item):
        with self.lock:
            _, icalendar, _ = libraries()
            request_id = item.get('requestId')
            try:
                object_id = str(uuid.UUID(request_id)) if request_id else str(uuid.uuid4())
            except (ValueError, TypeError, AttributeError):
                raise CalendarError('Invalid save reference.')
            uid = object_id+'@hemma-calendar'
            root = icalendar.Calendar()
            root.add('PRODID', '-//Family Planner//Calendar//EN')
            root.add('VERSION', '2.0')
            component = icalendar.Event()
            component.add('UID', uid)
            root.add_component(self._apply(component, item))
            url = urljoin(self._selected().rstrip('/')+'/', object_id+'.ics')
            with self._client() as client:
                try:
                    self._put(client, url, root, create=True)
                except CalendarError as error:
                    if error.status != 409 or not request_id:
                        raise
                    existing, _ = self._fetch(client, url)
                    old = existing.walk('VEVENT')[0]
                    new = root.walk('VEVENT')[0]
                    if any(str(old.get(field,''))!=str(new.get(field,'')) for field in ('SUMMARY','DESCRIPTION','LOCATION')) or identity(old['DTSTART']) != identity(new['DTSTART']) or identity(old['DTEND']) != identity(new['DTEND']):
                        raise CalendarError('This save request was already completed with different data. Refresh the calendar before trying again.',409)
                    return {'ok':True, 'alreadySaved':True}
            return {'ok':True}

    def _existing(self, client, token, expected_etag):
        reference = self._decode(token)
        root, etag = self._fetch(client, reference['url'])
        if not expected_etag or not etag or not hmac.compare_digest(str(etag), str(expected_etag)):
            raise CalendarError('The event has changed in iCloud. Refresh the calendar and reopen it.', 409)
        components = [c for c in root.walk('VEVENT') if str(c.get('UID', '')) == reference['uid']]
        if not components:
            raise CalendarError('The event no longer exists.', 409)
        return reference, root, etag, components

    def update(self, token, expected_etag, item):
        with self.lock, self._client() as client:
            reference, root, etag, components = self._existing(client, token, expected_etag)
            if reference['rid']:
                rid = reference['rid']
                exact = next((c for c in components if c.get('RECURRENCE-ID') is not None and identity(c['RECURRENCE-ID']) == rid), None)
                base = exact or next((c for c in components if c.get('RECURRENCE-ID') is None), None)
                if base is None:
                    raise CalendarError('Could not find the recurring occurrence.', 409)
                component = copy.deepcopy(base)
                for name in ['RRULE', 'RDATE', 'EXDATE', 'EXRULE', 'RECURRENCE-ID']:
                    component.pop(name, None)
                occurrence_start = parse_identity(rid)
                component.add('RECURRENCE-ID', occurrence_start)
                if exact is None:
                    base_start, base_end = base.decoded('DTSTART'), get_end(base)
                    if isinstance(occurrence_start, datetime) and isinstance(base_start, datetime) and base_start.tzinfo:
                        occurrence_start = occurrence_start.astimezone(base_start.tzinfo)
                    for name, value in [('DTSTART', occurrence_start), ('DTEND', occurrence_start+(base_end-base_start))]:
                        component.pop(name, None)
                        component.add(name, value)
                if exact is not None:
                    root.subcomponents.remove(exact)
                root.add_component(self._apply(component, item))
            else:
                self._apply(components[0], item)
            self._put(client, reference['url'], root, etag)
            return {'ok':True}

    def delete(self, token, expected_etag):
        with self.lock, self._client() as client:
            reference, root, etag, components = self._existing(client, token, expected_etag)
            if reference['rid']:
                rid = reference['rid']
                master = next((c for c in components if c.get('RECURRENCE-ID') is None), None)
                for component in list(components):
                    if component.get('RECURRENCE-ID') is not None and identity(component['RECURRENCE-ID']) == rid:
                        root.subcomponents.remove(component)
                if master is not None:
                    master.add('EXDATE', parse_identity(rid))
                    master.pop('LAST-MODIFIED', None)
                    master.add('LAST-MODIFIED', datetime.now(timezone.utc))
                if root.walk('VEVENT'):
                    self._put(client, reference['url'], root, etag)
                    return {'ok':True}
            response = client.request(reference['url'], method='DELETE', headers={'If-Match':etag})
            if response.status in (409, 412):
                raise CalendarError('The event was changed concurrently in iCloud. Refresh and try again.', 409)
            if response.status not in (200, 204):
                raise CalendarError('Could not delete the calendar event.', 502)
            return {'ok':True}

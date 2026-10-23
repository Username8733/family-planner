"""Provider contract tests with isolated HTTP fixtures; never contacts personal accounts."""
import json,tempfile,threading,uuid,time,base64,hashlib
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlsplit,parse_qs
from datetime import date
import calendar_sources as providers
from calendar_sources import CalendarSources
from online_calendar import ICloudCalendar,CalendarError

class Fixture(BaseHTTPRequestHandler):
    events={};ha_created=[];token_calls=[];failure=False;tokens=[]
    def log_message(self,*args):pass
    def send(self,data,status=200,content='application/json'):
        raw=data if isinstance(data,bytes) else json.dumps(data).encode()
        self.send_response(status);self.send_header('Content-Type',content);self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    def body(self):
        raw=self.rfile.read(int(self.headers.get('Content-Length',0)))
        return parse_qs(raw.decode()) if 'application/x-www-form-urlencoded' in self.headers.get('Content-Type','') else json.loads(raw or '{}')
    def check(self):
        assert self.headers.get('Authorization') in ('Bearer ha-test-token-not-real','Bearer test-access')
    def do_GET(self):
        path=urlsplit(self.path).path;q=parse_qs(urlsplit(self.path).query)
        if path=='/feed.ics':
            if self.failure:return self.send({},500)
            return self.send(b'BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\nUID:feed-test\r\nDTSTART;VALUE=DATE:20261030\r\nDTEND;VALUE=DATE:20261103\r\nSUMMARY:Person 5 - Break\r\nDESCRIPTION:Feed notes\r\nLOCATION:Public hall\r\nRRULE:FREQ=YEARLY;COUNT=2\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n',content='text/calendar')
        self.check()
        if path=='/api/calendars':return self.send([{'entity_id':'calendar.hem','name':'HA Home'}])
        if path=='/api/states':return self.send([{'entity_id':'calendar.hem','attributes':{'supported_features':1}}])
        if path=='/api/calendars/calendar.hem':return self.send([{'summary':'Person 4 - HA Dance','start':{'dateTime':'2026-10-24T12:00:00+02:00'},'end':{'dateTime':'2026-10-24T13:00:00+02:00'},'description':'HA notes','location':'HA hall'}])
        if path=='/google/users/me/calendarList':
            if 'pageToken' not in q:return self.send({'items':[{'id':'home@example.invalid','summary':'Google Home','accessRole':'owner'}],'nextPageToken':'second'})
            return self.send({'items':[{'id':'holidays','summary':'Holidays','accessRole':'reader'}]})
        if path=='/google/calendars/home%40example.invalid/events':
            # Google event pagination including recurring occurrence.
            if 'pageToken' not in q:return self.send({'items':list(self.events.values()),'nextPageToken':'last'})
            return self.send({'items':[{'id':'recurrence-instance','summary':'Person 5, Person 4 - Cinema','start':{'date':'2026-10-25'},'end':{'date':'2026-10-26'},'etag':'"r1"','recurringEventId':'series'}]})
        if path.startswith('/google/calendars/home%40example.invalid/events/'):
            return self.send(self.events[path.rsplit('/',1)[1]])
        self.send({},404)
    def do_POST(self):
        path=urlsplit(self.path).path;data=self.body()
        if path=='/token':
            self.token_calls.append(data)
            if data['grant_type']==['authorization_code']:
                assert data.get('code_verifier') and data['code']==['fixture-code']
                return self.send({'access_token':'test-access','refresh_token':'test-refresh','expires_in':3600})
            assert data['grant_type']==['refresh_token'] and data['refresh_token']==['test-refresh']
            return self.send({'access_token':'test-access','expires_in':3600})
        self.check()
        if path=='/api/services/calendar/create_event':
            self.ha_created.append(data);return self.send([])
        if path=='/google/calendars/home%40example.invalid/events':
            if data['id'] in self.events:return self.send({},409)
            self.events[data['id']]=dict(data,etag='"v1"');return self.send(self.events[data['id']],201)
        self.send({},404)
    def do_PATCH(self):
        self.check();data=self.body();eid=urlsplit(self.path).path.rsplit('/',1)[1]
        if self.headers.get('If-Match')!=self.events[eid]['etag']:return self.send({},412)
        self.events[eid].update(data,etag='"v2"');return self.send(self.events[eid])
    def do_DELETE(self):
        self.check();eid=urlsplit(self.path).path.rsplit('/',1)[1]
        if self.headers.get('If-Match')!=self.events[eid]['etag']:return self.send({},412)
        del self.events[eid];return self.send({},204)

with tempfile.TemporaryDirectory(prefix='hemma-providers-') as folder:
    server=ThreadingHTTPServer(('127.0.0.1',0),Fixture);threading.Thread(target=server.serve_forever,daemon=True).start()
    url='http://127.0.0.1:'+str(server.server_port)
    oldapi,oldtoken=providers.GOOGLE_API,providers.GOOGLE_TOKEN
    providers.GOOGLE_API=url+'/google';providers.GOOGLE_TOKEN=url+'/token'
    try:
        registry=CalendarSources(ICloudCalendar(Path(folder)/'icloud.json'))
        registry.add({'type':'ha','name':'HA','url':url,'token':'ha-test-token-not-real'})
        registry.add({'type':'ics','name':'Feed','url':url+'/feed.ics'})
        result=registry.add({'type':'google','clientId':'fixture.apps.googleusercontent.com','clientSecret':'fixture-secret'},url+'/callback')
        auth=parse_qs(urlsplit(result['authorizationUrl']).query);state=auth['state'][0]
        pending=registry.pending[state]
        challenge=base64.urlsafe_b64encode(hashlib.sha256(pending['verifier'].encode()).digest()).decode().rstrip('=')
        assert auth['code_challenge']==[challenge] and auth['code_challenge_method']==['S256']
        try:registry.google_callback('wrong','fixture-code');raise AssertionError('Bad OAuth state accepted')
        except CalendarError:pass
        registry.google_callback(state,'fixture-code')
        try:registry.google_callback(state,'fixture-code');raise AssertionError('OAuth callback replay accepted')
        except CalendarError:pass
        gs=next(s for s in registry.list()['sources'] if s['type']=='google')
        assert len(gs['calendars'])==2 and not gs['calendars'][1]['canCreate']
        registry.configure(gs['id'],{'selected':['home@example.invalid','holidays']})
        # Don't query the readonly fixture calendar; capability assertions suffice.
        registry.configure(gs['id'],{'selected':['home@example.invalid']})
        item={'sourceId':gs['id'],'calendarId':'home@example.invalid','summary':'Person 5 - Test',
              'date':'2026-10-24','endDate':'2026-10-24','time':'12:00','end':'13:00','requestId':str(uuid.uuid4()),'description':'First line\nSecond line','location':'Meeting room'}
        registry.mutate('POST',item);registry.mutate('POST',item)
        assert len(Fixture.events)==1
        d=registry.events('2026-10-01','2026-11-01')
        assert not d['errors'],d['errors']
        assert len(d['events'])==4,len(d['events'])
        google=next(e for e in d['events'] if e['summary']=='Person 5 - Test')
        assert google['date']=='2026-10-24' and google['time']=='12:00' and google['writable']
        assert google['description']==item['description'] and google['location']==item['location']
        assert next(e for e in d['events'] if e['summary'].endswith('Cinema'))['recurring']
        feed=next(e for e in d['events'] if e['sourceName']=='Feed')
        assert feed['endDate']=='2026-11-02' and not feed['writable'] and not feed['canDelete']
        assert feed['description']=='Feed notes' and feed['location']=='Public hall'
        update=dict(item,id=google['id'],etag=google['etag'],summary='Person 5 - Updated')
        update.pop('description');update.pop('location')
        registry.mutate('PUT',update)
        try:registry.mutate('PUT',update);raise AssertionError('Stale Google ETag accepted')
        except CalendarError as e:assert e.status==409
        updated=next(e for e in registry.events('2026-10-01','2026-11-01')['events'] if e['summary']=='Person 5 - Updated')
        assert updated['description']==item['description'] and updated['location']==item['location']
        registry.mutate('PUT',dict(update,id=updated['id'],etag=updated['etag'],description='Updated notes',location='Room B'))
        updated=next(e for e in registry.events('2026-10-01','2026-11-01')['events'] if e['summary']=='Person 5 - Updated')
        assert updated['description']=='Updated notes' and updated['location']=='Room B'
        registry.mutate('PUT',dict(update,id=updated['id'],etag=updated['etag'],description='',location=''))
        updated=next(e for e in registry.events('2026-10-01','2026-11-01')['events'] if e['summary']=='Person 5 - Updated')
        assert updated['description']=='' and updated['location']==''
        registry.mutate('DELETE',{'id':updated['id'],'etag':updated['etag']});assert not Fixture.events
        ha=next(s for s in registry.list()['sources'] if s['type']=='ha')
        hi=dict(item,sourceId=ha['id'],calendarId='calendar.hem',time='',end='',endDate='2026-10-26',requestId=str(uuid.uuid4()))
        registry.mutate('POST',hi);registry.mutate('POST',hi)
        assert len(Fixture.ha_created)==1 and Fixture.ha_created[0]['end_date']=='2026-10-27'
        assert Fixture.ha_created[0]['description']==item['description'] and Fixture.ha_created[0]['location']==item['location']
        haevent=next(e for e in d['events'] if e['sourceName']=='HA')
        assert haevent['description']=='HA notes' and haevent['location']=='HA hall'
        try:registry.mutate('DELETE',{'id':haevent['id'],'etag':''});raise AssertionError('Read-only HA event mutated')
        except CalendarError as e:assert e.status==403
        Fixture.failure=True
        partial=registry.events('2026-10-01','2026-11-01')
        assert len(partial['errors'])==1 and len(partial['events'])==2
        assert len(registry.events('2026-11-01','2026-12-01')['errors'])==1
        Fixture.failure=False
        registry.data['sources'][gs['id']]['expires']=0
        registry.events('2026-10-01','2026-11-01')
        assert Fixture.token_calls[-1]['grant_type']==['refresh_token']
        public=json.dumps(registry.list())
        assert all(secret not in public for secret in ['fixture-secret','test-refresh','test-access','ha-test-token-not-real','feed.ics'])
        assert registry.path.stat().st_mode&0o777==0o600
        fresh=CalendarSources(ICloudCalendar(Path(folder)/'icloud.json'))
        assert len(fresh.list()['sources'])==3
        assert len(fresh.events('2026-10-01','2026-11-01')['events'])==3
        registry.remove(gs['id'])
        assert len(registry.list()['sources'])==2
        print('PASS: Google OAuth state/PKCE, token refresh, pagination, shared recurring instances, CRUD, ETags and retry; HA read/create and capability limits; ICS recurring spans, partial failures, selections, secret isolation and restart.')
    finally:
        providers.GOOGLE_API,providers.GOOGLE_TOKEN=oldapi,oldtoken
        server.shutdown();server.server_close()

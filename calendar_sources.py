"""Multi-source calendars. Provider secrets are stored outside the served directory."""
import base64, hashlib, hmac, json, os, secrets, tempfile, threading, time, uuid
from contextlib import closing
from datetime import date, datetime, time as day_time, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode, urlsplit, quote
from urllib.request import Request, urlopen, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError
from zoneinfo import ZoneInfo
from online_calendar import ICloudCalendar, CalendarError, libraries, event_details

GOOGLE_API = 'https://www.googleapis.com/calendar/v3'
GOOGLE_TOKEN = 'https://oauth2.googleapis.com/token'
GOOGLE_AUTH = 'https://accounts.google.com/o/oauth2/v2/auth'
SCOPES = 'https://www.googleapis.com/auth/calendar.calendarlist.readonly https://www.googleapis.com/auth/calendar.events'

def valid_url(value):
    if not isinstance(value,str) or len(value)>4096:
        raise CalendarError('Enter a valid server address.')
    value=value.strip().replace('webcal://','https://')
    p=urlsplit(value)
    if p.scheme not in ('http','https') or not p.hostname or p.username or p.password or p.fragment:
        raise CalendarError('Use an http or https address without credentials in the URL.')
    return value

class NoRedirect(HTTPRedirectHandler):
    # Do not forward a bearer token or a private feed URL to another host.
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

def http(url, method='GET', payload=None, headers=None, form=False):
    data=None if payload is None else (urlencode(payload).encode() if form else json.dumps(payload).encode())
    hdr={'Accept':'application/json',**(headers or {})}
    if data is not None:hdr['Content-Type']='application/x-www-form-urlencoded' if form else 'application/json'
    try:
        with build_opener(NoRedirect).open(Request(url,data=data,headers=hdr,method=method),timeout=25) as r:
            raw=r.read(2_000_001)
            if len(raw)>2_000_000:raise CalendarError('The calendar response is too large.',422)
            return r.status,raw,dict(r.headers)
    except HTTPError as e:
        # Upstream bodies and URLs may contain account information. Never surface them.
        if e.code in (409,412):raise CalendarError('The event has changed. Refresh the calendar and try again.',409)
        if e.code in (401,403):raise CalendarError('The calendar denied access. Check the connection and permissions.',403)
        raise CalendarError('The calendar service could not complete the operation (HTTP '+str(e.code)+').',502)
    except (OSError,TimeoutError):
        raise CalendarError('The calendar service could not be reached. Check the server address and connection.',502)

def json_http(*args,**kwargs):
    status,raw,headers=http(*args,**kwargs)
    return json.loads(raw) if raw.strip() else {},headers

def interval(first,last,tz):
    try:
        a,b=date.fromisoformat(first),date.fromisoformat(last)
        if a.year<2000 or b.year>2101 or not 0<(b-a).days<=95:raise ValueError()
        return datetime.combine(a,day_time(),tz),datetime.combine(b,day_time(),tz)
    except (ValueError,TypeError):raise CalendarError('Enter a valid date range of up to 95 days.')

class CalendarSources:
    def __init__(self, primary, filename=None):
        self.primary=primary
        self.path=Path(filename or primary.config_file.parent/'sources.json')
        self.lock=threading.RLock()
        self.data=json.loads(self.path.read_text()) if self.path.exists() else {'key':secrets.token_hex(32),'sources':{}}
        self.pending={}
        self.adapters={}
        self.ha_cache={}
        self.create_receipts={}
        if not self.path.exists():self._save()
    def _save(self):
        self.path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        fd,name=tempfile.mkstemp(prefix='.sources-',dir=self.path.parent)
        try:
            os.fchmod(fd,0o600)
            with os.fdopen(fd,'w') as f:
                json.dump(self.data,f);f.flush();os.fsync(f.fileno())
            os.replace(name,self.path)
        finally:
            if os.path.exists(name):os.unlink(name)
    def _sign(self,data):
        raw=base64.urlsafe_b64encode(json.dumps(data,separators=(',',':')).encode()).decode().rstrip('=')
        sig=hmac.new(self.data['key'].encode(),raw.encode(),hashlib.sha256).hexdigest()
        return raw+'.'+sig
    def _decode(self,value):
        try:
            raw,sig=value.rsplit('.',1)
            if not hmac.compare_digest(sig,hmac.new(self.data['key'].encode(),raw.encode(),hashlib.sha256).hexdigest()):raise ValueError()
            d=json.loads(base64.urlsafe_b64decode(raw+'='*(-len(raw)%4)))
            if not all(isinstance(d.get(k),str) for k in ['source','calendar','remote']):raise ValueError()
            return d
        except (ValueError,TypeError,KeyError,AttributeError):
            raise CalendarError('Invalid event reference.',400)
    def _source(self,sid):
        if sid=='icloud':
            status=self.primary.status()
            cid=status['calendarId']
            return {'type':'icloud','name':'iCloud','timezone':status['timezone'],
                    'selected':[cid] if cid and self.data.get('icloud_enabled',True) else [],
                    'calendars':[{'id':cid,'name':status['calendarName'],'canCreate':True,'canUpdate':True,'canDelete':True}] if cid else []}
        if sid not in self.data['sources']:raise CalendarError('The calendar source does not exist.',404)
        return self.data['sources'][sid]
    def _calendar(self,s,cid):
        c=next((c for c in s.get('calendars',[]) if c['id']==cid),None)
        if not c or cid not in s.get('selected',[]):raise CalendarError('Select the calendar in Settings first.',409)
        return c
    def list(self):
        with self.lock:
            sources=[]
            for sid in ['icloud',*self.data['sources']]:
                s=self._source(sid)
                if sid=='icloud' and not self.primary.status()['configured']:continue
                sources.append({'id':sid,'type':s['type'],'name':s['name'],'timezone':s.get('timezone','Europe/Stockholm'),
                                'selected':s.get('selected',[]),'calendars':[{k:v for k,v in c.items() if k in ['id','name','canCreate','canUpdate','canDelete']} for c in s.get('calendars',[])],
                                'connected':bool(s.get('refresh_token')) if s['type']=='google' else True,
                                'account':self.primary.config.get('username','') if sid=='icloud' else ''})
            return {'sources':sources}
    def _adapter(self,sid,s,c):
        if sid=='icloud':return self.primary
        cache=(sid,c['id'])
        if cache not in self.adapters:
            a=ICloudCalendar(self.path.parent/('unused-'+sid+'.json'),server_url=s['url'])
            a.config={'username':s['username'],'password':s['password'],'timezone':s['timezone'],
                      'calendar_id':c['id'],'calendar_url':c['url'],'calendar_name':c['name']}
            a.sign_key=self.data['key']
            self.adapters[cache]=a
        return self.adapters[cache]
    def add(self,body,redirect_uri=None):
        kind=body.get('type');name=str(body.get('name','')).strip()[:100]
        if kind not in ('caldav','ha','ics','google'):raise CalendarError('Choose a calendar provider.')
        try:ZoneInfo(body.get('timezone','Europe/Stockholm'))
        except (ValueError,KeyError,TypeError):raise CalendarError('Enter a valid time zone.')
        sid=uuid.uuid4().hex
        s={'type':kind,'name':name or {'caldav':'CalDAV','ha':'Home Assistant','ics':'ICS','google':'Google'}[kind],
           'timezone':body.get('timezone','Europe/Stockholm'),'selected':[],'calendars':[]}
        with self.lock:
            if kind=='google':
                client_id=str(body.get('clientId','')).strip();secret=str(body.get('clientSecret','')).strip()
                if not client_id.endswith('.apps.googleusercontent.com') or len(secret)<8:raise CalendarError('Enter your Google OAuth Client ID and Client secret.')
                s.update(client_id=client_id,client_secret=secret)
                state=secrets.token_urlsafe(32);verifier=secrets.token_urlsafe(48)
                challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
                self.pending[state]={'source':sid,'config':s,'verifier':verifier,'redirect':redirect_uri,'expires':time.time()+600}
                url=GOOGLE_AUTH+'?'+urlencode({'client_id':client_id,'redirect_uri':redirect_uri,'response_type':'code','scope':SCOPES,
                    'access_type':'offline','prompt':'consent','state':state,'code_challenge':challenge,'code_challenge_method':'S256'})
                return {'authorizationUrl':url,'sourceId':sid}
            s['url']=valid_url(body.get('url'))
            if kind!='ics':s['url']=s['url'].rstrip('/')
            if kind=='caldav':
                s['username']=str(body.get('username','')).strip();s['password']=str(body.get('password',''))
                if not s['username'] or not s['password']:raise CalendarError('Enter a username and password.')
                a=ICloudCalendar(self.path.parent/('unused-'+sid+'.json'),server_url=s['url'])
                a.config={'username':s['username'],'password':s['password']}
                found=a._discover()
                s['calendars']=[dict(id=c['id'],name=c['name'],url=c['url'],canCreate=True,canUpdate=True,canDelete=True) for c in found.values()]
            elif kind=='ha':
                s['token']=str(body.get('token','')).strip()
                if len(s['token'])<20:raise CalendarError('Enter a Home Assistant long-lived access token.')
                calendars,_=json_http(s['url']+'/api/calendars',headers={'Authorization':'Bearer '+s['token']})
                states,_=json_http(s['url']+'/api/states',headers={'Authorization':'Bearer '+s['token']})
                features={x['entity_id']:x.get('attributes',{}).get('supported_features',0) for x in states}
                s['calendars']=[{'id':c['entity_id'],'name':c['name'],'canCreate':bool(features.get(c['entity_id'],0)&1),'canUpdate':bool(features.get(c['entity_id'],0)&4),'canDelete':bool(features.get(c['entity_id'],0)&2)} for c in calendars]
            elif kind=='ics':
                _,raw,_=http(s['url'])
                _,ical,_=libraries()
                ical.Calendar.from_ical(raw) # Validate before storing a secret URL.
                s['calendars']=[{'id':'feed','name':s['name'],'canCreate':False,'canUpdate':False,'canDelete':False}]
            if len(s['calendars'])==1:s['selected']=[s['calendars'][0]['id']]
            self.data['sources'][sid]=s;self._save()
            return self.list()
    def google_callback(self,state,code):
        with self.lock:
            p=self.pending.pop(state,None)
            if not p or time.time()>p['expires'] or not code:raise CalendarError('Google sign-in expired or was cancelled. Try again.',400)
            s=p['config']
            token,_=json_http(GOOGLE_TOKEN,'POST',{'code':code,'client_id':s['client_id'],'client_secret':s['client_secret'],
                         'redirect_uri':p['redirect'],'grant_type':'authorization_code','code_verifier':p['verifier']},form=True)
            if not token.get('refresh_token'):raise CalendarError('Google did not grant persistent access. Reconnect and grant calendar access.',409)
            s.update(refresh_token=token['refresh_token'],access_token=token['access_token'],expires=time.time()+token.get('expires_in',3600)-60)
            sid=p['source'];self.data['sources'][sid]=s
            try:s['calendars']=self._google_calendars(s)
            except Exception:
                del self.data['sources'][sid];raise
            if len(s['calendars'])==1:s['selected']=[s['calendars'][0]['id']]
            self._save()
    def _google(self,s,path,method='GET',payload=None,etag=None):
        if s.get('expires',0)<=time.time():
            token,_=json_http(GOOGLE_TOKEN,'POST',{'client_id':s['client_id'],'client_secret':s['client_secret'],
                    'refresh_token':s['refresh_token'],'grant_type':'refresh_token'},form=True)
            s.update(access_token=token['access_token'],expires=time.time()+token.get('expires_in',3600)-60);self._save()
        hdr={'Authorization':'Bearer '+s['access_token']}
        if etag:hdr['If-Match']=etag
        return json_http(GOOGLE_API+path,method,payload,headers=hdr)[0]
    def _google_calendars(self,s):
        result=[];page=None
        for _ in range(100):
            d=self._google(s,'/users/me/calendarList?'+urlencode({'maxResults':250,**({'pageToken':page} if page else {})}))
            for c in d.get('items',[]):
                writable=c.get('accessRole') in ('owner','writer')
                result.append({'id':c['id'],'name':c.get('summaryOverride',c.get('summary','Google')),'canCreate':writable,'canUpdate':writable,'canDelete':writable})
            page=d.get('nextPageToken')
            if not page:return result
        raise CalendarError('Too many calendars in the account.',422)
    def configure(self,sid,body):
        with self.lock:
            if sid=='icloud':
                # Keep the existing private configuration and signed references.
                ids=body.get('selected',[])
                if not isinstance(ids,list) or len(ids)>1:
                    raise CalendarError('Choose an iCloud calendar.')
                if ids and (ids[0]!=self.primary.status()['calendarId'] or body.get('timezone','Europe/Stockholm')!=self.primary.status()['timezone']):
                    self.primary.select(ids[0],body.get('timezone','Europe/Stockholm'))
                self.data['icloud_enabled']=bool(ids);self._save()
                return self.list()
            s=self._source(sid);selected=body.get('selected')
            if not isinstance(selected,list) or not all(isinstance(cid,str) and any(c['id']==cid for c in s['calendars']) for cid in selected):raise CalendarError('Invalid calendar selection.')
            s['selected']=list(dict.fromkeys(selected));self._save();return self.list()
    def remove(self,sid):
        with self.lock:
            if sid=='icloud':self.primary.disconnect()
            else:self.data['sources'].pop(sid,None)
            self.adapters={k:v for k,v in self.adapters.items() if k[0]!=sid};self._save()
            return self.list()
    def _normalize(self,s,start,end,summary,remote,etag='',recurring=False,writable=False,description='',location=''):
        _,ical,_=libraries()
        root=ical.Calendar();e=ical.Event();e.add('UID',remote);e.add('DTSTART',start);e.add('DTEND',end);e.add('SUMMARY',summary);root.add_component(e)
        a=ICloudCalendar(self.path.parent/'unused-normalizer.json')
        a.config={'timezone':s['timezone'],'calendar_id':'normalize'}
        d=a._serialize(e,root,'https://invalid.example/event',etag)
        return dict(d,id=remote,recurring=recurring,writable=writable,description=description or '',location=location or '')
    def _read(self,sid,s,c,first,last):
        tz=ZoneInfo(s['timezone']);a,b=interval(first,last,tz)
        if s['type'] in ('icloud','caldav'):
            return self._adapter(sid,s,c).events(first,last)['events']
        if s['type']=='google':
            output=[];page=None
            for _ in range(100):
                params={'timeMin':a.isoformat(),'timeMax':b.isoformat(),'singleEvents':'true','maxResults':2500,'timeZone':s['timezone']}
                if page:params['pageToken']=page
                result=self._google(s,'/calendars/'+quote(c['id'],safe='')+'/events?'+urlencode(params))
                for e in result.get('items',[]):
                    if e.get('status')=='cancelled':continue
                    def dt(v):return date.fromisoformat(v['date']) if 'date' in v else datetime.fromisoformat(v['dateTime'].replace('Z','+00:00'))
                    output.append(self._normalize(s,dt(e['start']),dt(e['end']),e.get('summary','(Untitled)'),e['id'],e.get('etag',''),bool(e.get('recurringEventId')),c['canUpdate'] and bool(e.get('etag')) and not e.get('locked',False),description=e.get('description',''),location=e.get('location','')))
                page=result.get('nextPageToken')
                if not page:return output
            raise CalendarError('Too many calendar events.',422)
        if s['type']=='ha':
            result,_=json_http(s['url']+'/api/calendars/'+quote(c['id'],safe='')+'?'+urlencode({'start':a.isoformat(),'end':b.isoformat()}),headers={'Authorization':'Bearer '+s['token']})
            def dt(v):
                if isinstance(v,dict):v=v.get('dateTime',v.get('date'))
                return date.fromisoformat(v) if len(v)==10 else datetime.fromisoformat(v.replace('Z','+00:00'))
            output=[]
            for e in result:
                fingerprint=hashlib.sha256(json.dumps(e,sort_keys=True).encode()).hexdigest()
                remote=json.dumps({'uid':e.get('uid'),'rid':e.get('recurrence_id'),'day':dt(e['start']).isoformat()[:10]},sort_keys=True)
                writable=bool(e.get('uid')) and (c['canUpdate'] or c['canDelete'])
                self.ha_cache[(sid,c['id'],remote)]=e
                output.append(self._normalize(s,dt(e['start']),dt(e['end']),e.get('summary','(Untitled)'),remote,fingerprint,bool(e.get('recurrence_id')),writable,description=e.get('description',''),location=e.get('location','')))
            return output
        if s['type']=='ics':
            _,raw,_=http(s['url']);_,ical,rec= libraries();root=ical.Calendar.from_ical(raw)
            helper=ICloudCalendar(self.path.parent/'unused-normalizer.json');helper.config={'timezone':s['timezone'],'calendar_id':'feed'}
            events=[]
            for e in rec.of(root).between(a,b):
                if str(e.get('STATUS','')).upper()=='CANCELLED':continue
                d=helper._serialize(e,root,'https://invalid.example/feed','');d['id']=hashlib.sha256((str(e.get('UID'))+str(e.get('RECURRENCE-ID',e.get('DTSTART')))).encode()).hexdigest()
                events.append(d)
                if len(events)>2500:raise CalendarError('Too many calendar events.',422)
            return events
    def events(self,first,last):
        with self.lock:
            interval(first,last,timezone.utc)
            output=[];errors=[]
            for source in self.list()['sources']:
                sid=source['id'];s=self._source(sid)
                for c in s['calendars']:
                    if c['id'] not in s['selected']:continue
                    source_key=sid+':'+c['id']
                    try:
                        records=self._read(sid,s,c,first,last)
                        for record in records:
                            rid=record['id']
                            output.append(dict(record,id=self._sign({'source':sid,'calendar':c['id'],'remote':rid}),
                                   sourceId=sid,calendarId=c['id'],sourceKey=source_key,sourceName=s['name'],calendarName=c['name'],
                                   canDelete=c['canDelete'] and record.get('writable',False),canUpdate=c['canUpdate'] and record.get('writable',False)))
                    except Exception as e:
                        errors.append({'sourceKey':source_key,'name':s['name']+' · '+c['name'],
                                       'error':str(e) if isinstance(e,CalendarError) else 'Could not fetch the calendar. Check the connection.'})
            return {'events':output,'errors':errors}
    def _ha_ws(self,s,command):
        import websocket
        parts=urlsplit(s['url'])
        ws_url=('wss' if parts.scheme=='https' else 'ws')+'://'+parts.netloc+parts.path+'/api/websocket'
        try:
            with closing(websocket.create_connection(ws_url,timeout=25,suppress_origin=True)) as ws:
                if json.loads(ws.recv()).get('type')!='auth_required':raise CalendarError('HA denied the WebSocket connection.',502)
                ws.send(json.dumps({'type':'auth','access_token':s['token']}))
                if json.loads(ws.recv()).get('type')!='auth_ok':raise CalendarError('The calendar denied access. Check the connection and permissions.',403)
                ws.send(json.dumps(dict(command,id=1)))
                for _ in range(20):
                    reply=json.loads(ws.recv())
                    if reply.get('id')!=1:continue
                    if not reply.get('success'):
                        raise CalendarError('HA rejected the change. Check the calendar capabilities and permissions.',409)
                    return {'saved':True}
                raise CalendarError('HA did not respond to the change.',502)
        except CalendarError:raise
        except Exception:raise CalendarError('The HA calendar connection could not complete the change. Refresh before trying again.',502)

    def _payload(self,s,item,existing=None):
        helper=ICloudCalendar(self.path.parent/'unused-normalizer.json');helper.config={'timezone':s['timezone']}
        component=None
        if existing:
            _,ical,_=libraries();component=ical.Event()
            def parse(value):
                if isinstance(value,dict):value=value.get('date',value.get('dateTime'))
                return date.fromisoformat(value) if len(value)==10 else datetime.fromisoformat(value.replace('Z','+00:00'))
            component.add('DTSTART',parse(existing['start']));component.add('DTEND',parse(existing['end']))
        start,end=helper._dates(item,component)
        details=event_details(item,existing)
        if isinstance(start,datetime):
            return {'summary':item['summary'],'start':{'dateTime':start.isoformat(),'timeZone':s['timezone']},'end':{'dateTime':end.isoformat(),'timeZone':s['timezone']},**details}
        return {'summary':item['summary'],'start':{'date':start.isoformat()},'end':{'date':end.isoformat()},**details}
    def mutate(self,method,item):
        with self.lock:
            if method=='POST':sid,cid=item.get('sourceId'),item.get('calendarId');remote=None
            else:
                ref=self._decode(item.get('id'));sid,cid,remote=ref['source'],ref['calendar'],ref['remote']
            s=self._source(sid);c=self._calendar(s,cid)
            feature={'POST':'canCreate','PUT':'canUpdate','DELETE':'canDelete'}[method]
            if not c.get(feature):raise CalendarError('This calendar does not support this change. Open it with the provider.',403)
            if method!='DELETE':
                if not isinstance(item.get('summary'),str) or not item['summary'].strip() or len(item['summary'])>512:raise CalendarError('Enter an event with up to 512 characters.')
            if s['type'] in ('icloud','caldav'):
                adapter=self._adapter(sid,s,c)
                if method=='POST':return adapter.create(item)
                if method=='PUT':return adapter.update(remote,item.get('etag',''),item)
                return adapter.delete(remote,item.get('etag',''))
            if s['type']=='google':
                path='/calendars/'+quote(cid,safe='')+'/events'
                if method=='POST':
                    try:request_id=str(uuid.UUID(item['requestId']))
                    except (ValueError,KeyError,TypeError):raise CalendarError('Invalid save reference.')
                    payload=self._payload(s,item);payload['id']=hashlib.sha256(request_id.encode()).hexdigest()
                    try:self._google(s,path,'POST',payload)
                    except CalendarError as e:
                        if e.status!=409:raise
                        previous=self._google(s,path+'/'+payload['id'])
                        if any(previous.get(k,'' if k in ('description','location') else None)!=payload[k] for k in ('summary','start','end','description','location') if k in payload):raise
                    return {'saved':True}
                if not item.get('etag'):raise CalendarError('Refresh the calendar before changing the event.',409)
                payload=None
                if method=='PUT':
                    existing=self._google(s,path+'/'+quote(remote,safe=''))
                    if existing.get('etag')!=item['etag']:raise CalendarError('The event has changed. Refresh the calendar and try again.',409)
                    payload=self._payload(s,item,existing)
                self._google(s,path+'/'+quote(remote,safe=''),'PATCH' if method=='PUT' else 'DELETE',payload,etag=item['etag'])
                return {'saved':True}
            if s['type']=='ha' and method in ('PUT','DELETE'):
                try:
                    ref=json.loads(remote)
                    if not ref.get('uid'):raise ValueError()
                    # Re-read the occurrence and reject concurrent edits before
                    # calling HA. HA has no atomic If-Match for calendar commands.
                    day=date.fromisoformat(ref['day'])
                    current=self._read(sid,s,c,day.isoformat(),(day+timedelta(days=1)).isoformat())
                    event=next((e for e in current if e['id']==remote),None)
                    if not event or event['etag']!=item.get('etag'):
                        raise CalendarError('The event has changed. Refresh the calendar and try again.',409)
                except (ValueError,KeyError,TypeError):raise CalendarError('The event has no valid HA reference.',409)
                command={'type':'calendar/event/'+('update' if method=='PUT' else 'delete'),'entity_id':cid,'uid':ref['uid']}
                if ref.get('rid'):command['recurrence_id']=ref['rid']
                if method=='PUT':
                    original=self.ha_cache[(sid,cid,remote)]
                    payload=self._payload(s,item,original)
                    command['event']={'summary':payload['summary'],'dtstart':payload['start'].get('date',payload['start'].get('dateTime')),'dtend':payload['end'].get('date',payload['end'].get('dateTime'))}
                    for field in ('description','location'):
                        if field in payload:command['event'][field]=payload[field]
                        elif original.get(field) is not None:command['event'][field]=original[field]
                return self._ha_ws(s,command)
            if s['type']=='ha' and method=='POST':
                payload=self._payload(s,item);start,end=payload['start'],payload['end']
                data={'entity_id':cid,'summary':payload['summary'],**{k:payload[k] for k in ('description','location') if k in payload}}
                data.update({'start_date':start['date'],'end_date':end['date']} if 'date' in start else {'start_date_time':start['dateTime'],'end_date_time':end['dateTime']})
                # HA create_event has no idempotency key; cache confirmed requests.
                request_id=item.get('requestId')
                if not isinstance(request_id,str):raise CalendarError('Invalid save reference.')
                receipt=(sid,cid,request_id)
                fingerprint=hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()
                if receipt in self.create_receipts:
                    if self.create_receipts[receipt]!=fingerprint:raise CalendarError('The save reference is already in use.',409)
                    return {'saved':True,'alreadySaved':True}
                json_http(s['url']+'/api/services/calendar/create_event','POST',data,headers={'Authorization':'Bearer '+s['token']})
                self.create_receipts[receipt]=fingerprint
                return {'saved':True}
            raise CalendarError('This calendar is read only.',403)

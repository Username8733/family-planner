import os
import sys,json,time,subprocess,tempfile,urllib.request,base64
from pathlib import Path
import websocket
root=Path(__file__).resolve().parent;qa=root/'qa';qa.mkdir(exist_ok=True)

# Isolated real CalDAV + application servers; no Apple account is involved.
import atexit,socket,threading
import caldav
from datetime import date,datetime
from zoneinfo import ZoneInfo
from online_calendar import ICloudCalendar,CalendarError
from serve import CalendarHTTPServer,Handler
Handler.log_message=lambda *args:None
fixture=tempfile.TemporaryDirectory(prefix='hemma-online-browser-')
fixture_root=Path(fixture.name)
sock=socket.socket();sock.bind(('127.0.0.1',0));dav_port=sock.getsockname()[1];sock.close()
dav_log=(fixture_root/'dav.log').open('w+')
dav_proc=subprocess.Popen([sys.executable,'-m','xandikos.web','--defaults','--no-detect-systemd','-d',str(fixture_root/'dav'),'--state-dir',str(fixture_root/'state'),'-l','127.0.0.1','-p',str(dav_port)],stdout=dav_log,stderr=dav_log)
for _ in range(100):
 try:urllib.request.urlopen(f'http://127.0.0.1:{dav_port}/',timeout=.2);break
 except Exception:time.sleep(.05)
dav_url=f'http://127.0.0.1:{dav_port}/'
with caldav.DAVClient(url=dav_url,username='test@example.invalid',password='local-test-password',require_tls=False,enable_rfc6764=False) as client:
 cal=client.get_principal().get_calendars()[0]
 for uid,title,day in [('dans','Person 5 - Dance',24),('bio','Person 5, Person 4 - Cinema',24),('unknown','Guest, Person 5 - Visit',25),('no-prefix','Family dinner',26),('dash','Person 5 - Home - Planning',27)]:
  cal.add_event(uid=uid,summary=title,dtstart=date(2026,10,day),dtend=date(2026,10,day+1))
 cal.add_event(uid='range',summary='Person 5, Person 4 - Autumn break',dtstart=date(2026,10,29),dtend=date(2026,11,3))
backend=ICloudCalendar(fixture_root/'private/icloud.json',server_url=dav_url)
backend.connect('test@example.invalid','local-test-password')
backend.select(backend.calendars()['calendars'][0]['id'])
app_host=os.environ.get('QA_HTTP_HOST','127.0.0.1')
app_server=CalendarHTTPServer(('127.0.0.1',0),root/'dist',backend=backend,public_host=app_host)
threading.Thread(target=app_server.serve_forever,daemon=True).start()
app_url=f'http://{app_host}:{app_server.server_port}/'
def cleanup_online():
 app_server.shutdown();app_server.server_close();dav_proc.terminate();dav_proc.wait(timeout=10);dav_log.close();fixture.cleanup()
atexit.register(cleanup_online)

with tempfile.TemporaryDirectory(prefix='browser-',dir=qa) as temp:
 proc=subprocess.Popen([os.environ.get('BRAVE_BINARY','/Applications/Brave Browser.app/Contents/MacOS/Brave Browser'),'--headless','--no-proxy-server','--host-resolver-rules=MAP planner.test 127.0.0.1','--disable-gpu','--no-first-run','--disable-background-networking','--remote-debugging-address=127.0.0.1','--remote-debugging-port=0','--user-data-dir='+temp,'about:blank'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 try:
  for _ in range(100):
   f=Path(temp)/'DevToolsActivePort'
   if f.exists() and f.read_text().strip():break
   time.sleep(.1)
  port=f.read_text().splitlines()[0]
  targets=json.load(urllib.request.urlopen('http://127.0.0.1:'+port+'/json',timeout=4))
  ws=websocket.create_connection(targets[0]['webSocketDebuggerUrl'],suppress_origin=True,timeout=20);seq=0;errors=[];network=[]
  def call(method,params=None):
   global seq
   seq+=1;ws.send(json.dumps({'id':seq,'method':method,'params':params or {}}))
   while True:
    r=json.loads(ws.recv())
    if r.get('method')=='Runtime.exceptionThrown':errors.append(r['params']['exceptionDetails'].get('text','Runtime exception'))
    if r.get('method')=='Network.requestWillBeSent':network.append(r['params']['request']['url'])
    if r.get('id')==seq:
     if 'error' in r:raise RuntimeError(r['error']['message'])
     return r.get('result',{})
  def ev(code):
   r=call('Runtime.evaluate',{'expression':code,'returnByValue':True,'awaitPromise':True})
   if r.get('exceptionDetails'):raise RuntimeError(str(r['exceptionDetails']))
   return r.get('result',{}).get('value')
  call('Page.enable');call('Runtime.enable');call('Network.enable')


  def until(code):
   for _ in range(200):
    if ev("typeof onlineState!=='undefined'&&("+code+")"):return
    time.sleep(.04)
   raise AssertionError('Timeout: '+code)
  call('Emulation.setDeviceMetricsOverride',{'width':1440,'height':1000,'deviceScaleFactor':1,'mobile':False})
  call('Page.navigate',{'url':app_url})
  until("sharedSettings.ready&&onlineState.sources.length===1")
  ev("document.getElementById('columns').click();document.getElementById('setting-calendar-mode').value='mixed';document.getElementById('save-columns').click()")
  until("!document.getElementById('column-editor').open&&!onlineState.loading&&onlineState.records.length===6")
  note="Bring a notebook.\nMeet by the entrance.\n<img src=x onerror=alert('unsafe')>"
  place="Community hall, Room B"
  ev("document.getElementById('add').click();document.getElementById('event-source').value=sourceChoice('icloud',onlineState.sources[0].selected[0]);document.getElementById('event-source').dispatchEvent(new Event('change'));document.getElementById('title').value='Notes test';document.getElementById('date').value='2026-10-28';document.getElementById('end-date').value='2026-10-28';document.getElementById('event-description').value="+json.dumps(note)+";document.getElementById('event-location').value="+json.dumps(place)+";document.getElementById('save-event').click()")
  until("!document.getElementById('editor').open&&!onlineState.loading&&calendarEvents().some(e=>e.title==='Notes test')")
  assert ev("calendarEvents().find(e=>e.title==='Notes test').description==="+json.dumps(note))
  assert ev("calendarEvents().find(e=>e.title==='Notes test').location==="+json.dumps(place))
  ev("openDay('2026-10-28')")
  assert ev("document.querySelector('#day-events .has-details .day-extra').textContent.includes('Community hall')")
  assert ev("document.querySelectorAll('#day-events img').length===0")
  ev("[...document.querySelectorAll('#day-events .day-event')].find(b=>b.querySelector('strong').textContent==='Notes test').click()")
  assert ev("document.getElementById('event-description').value==="+json.dumps(note))
  assert ev("document.getElementById('event-location').value==="+json.dumps(place))
  for label,w,h in [('desktop',1440,1000),('phone',390,844)]:
   call('Emulation.setDeviceMetricsOverride',{'width':w,'height':h,'deviceScaleFactor':1,'mobile':False});time.sleep(.05)
   for mode in ['light','dark']:
    ev("appearance={theme:'ios',mode:"+json.dumps(mode)+"};applyAppearance()")
    fit=ev("(()=>{const d=document.getElementById('editor'),n=document.getElementById('event-description'),l=document.getElementById('event-location');const save=document.getElementById('save-event').getBoundingClientRect(),box=d.getBoundingClientRect();return {saveVisible:save.top>=box.top&&save.bottom<=box.bottom,noOuterScroll:d.scrollHeight<=d.clientHeight+1,notesFit:n.clientWidth<=n.parentElement.clientWidth,locationFit:l.clientWidth<=l.parentElement.clientWidth}})()")
    assert all(fit.values()),str((label,mode,fit))
    ev("document.getElementById('event-description').scrollIntoView({block:'end'})")
    shot=call('Page.captureScreenshot',{'format':'png','captureBeyondViewport':False})
    (qa/('event-details-'+label+'-'+mode+'.png')).write_bytes(base64.b64decode(shot['data']))
  ev("document.getElementById('event-description').value='Updated notes';document.getElementById('event-location').value='Hall C';document.getElementById('save-event').click()")
  until("!document.getElementById('editor').open&&!onlineState.loading&&calendarEvents().find(e=>e.title==='Notes test')?.location==='Hall C'")
  assert ev("calendarEvents().find(e=>e.title==='Notes test').description==='Updated notes'")
  ev("document.getElementById('close-day').click();openEvent(calendarEvents().find(e=>e.title==='Notes test'),'2026-10-28','family');document.getElementById('event-description').value='';document.getElementById('event-location').value='';document.getElementById('save-event').click()")
  until("!document.getElementById('editor').open&&!onlineState.loading&&calendarEvents().find(e=>e.title==='Notes test')?.description===''")
  assert ev("calendarEvents().find(e=>e.title==='Notes test').location===''")
  # Local activities use the same fields and share them through the server.
  ev("openCell('2026-10-29','family');document.getElementById('title').value='Local details';document.getElementById('event-description').value='Local notes';document.getElementById('event-location').value='Local room';document.getElementById('save-event').click()")
  until("!document.getElementById('editor').open&&!sharedSettings.dirty&&!sharedSettings.inFlight")
  stored=app_server.planner_state.get()['state']
  local=next(e for e in stored['events'] if e['title']=='Local details')
  assert local['description']=='Local notes' and local['location']=='Local room'
  ev("openEvent(events.find(e=>e.title==='Local details'),'2026-10-29','family')")
  assert ev("document.getElementById('event-description').value==='Local notes'&&document.getElementById('event-location').value==='Local room'")
  ev("document.getElementById('close').click()")
  call('Page.reload');until("sharedSettings.ready&&events.some(e=>e.title==='Local details')&&!onlineState.loading")
  assert ev("events.find(e=>e.title==='Local details').description==='Local notes'&&events.find(e=>e.title==='Local details').location==='Local room'")
  assert not errors,errors
  print('PASS: online notes/location create, read, edit and clear; safe day preview; responsive editor in light/dark; local details saved on server and retained on reload.')
  call('Browser.close');proc.wait(timeout=15)
 finally:
  if proc.poll() is None:proc.terminate();proc.wait(timeout=15)

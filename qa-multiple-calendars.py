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
 for uid,title,day in [('dans','Person 5 - Dans',24),('bio','Person 5, Person 4 - Bio',24),('unknown','Sven, Person 5 - Besök',25),('no-prefix','Familjemiddag',26),('dash','Person 5 - Hemma - Planering',27)]:
  cal.add_event(uid=uid,summary=title,dtstart=date(2026,10,day),dtend=date(2026,10,day+1))
 cal.add_event(uid='range',summary='Person 5, Person 4 - Höstlov',dtstart=date(2026,10,29),dtend=date(2026,11,3))
backend=ICloudCalendar(fixture_root/'private/icloud.json',server_url=dav_url)
backend.connect('test@example.invalid','local-test-password')
backend.select(backend.calendars()['calendars'][0]['id'])
app_server=CalendarHTTPServer(('127.0.0.1',0),root/'dist',backend=backend)
threading.Thread(target=app_server.serve_forever,daemon=True).start()
app_url=f'http://127.0.0.1:{app_server.server_port}/'
def cleanup_online():
 app_server.shutdown();app_server.server_close();dav_proc.terminate();dav_proc.wait(timeout=10);dav_log.close();fixture.cleanup()
atexit.register(cleanup_online)

with tempfile.TemporaryDirectory(prefix='browser-',dir=qa) as temp:
 proc=subprocess.Popen([os.environ.get('BRAVE_BINARY','/Applications/Brave Browser.app/Contents/MacOS/Brave Browser'),'--headless','--disable-gpu','--no-first-run','--disable-background-networking','--remote-debugging-address=127.0.0.1','--remote-debugging-port=0','--user-data-dir='+temp,'about:blank'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
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
   for _ in range(180):
    if ev("typeof onlineState!=='undefined'&&("+code+")"):return
    time.sleep(.05)
   raise AssertionError('Timeout: '+code)
  call('Emulation.setDeviceMetricsOverride',{'width':1440,'height':1000,'deviceScaleFactor':1,'mobile':False})
  call('Page.navigate',{'url':app_url})
  until("onlineState.available&&onlineState.sources.length===1")
  ev("month=new Date(2026,9,1);render();window.qaPeople=JSON.stringify(people.map(({id,name,color})=>({id,name,color})));window.qaLocal=JSON.stringify(events)")
  ev("document.getElementById('columns').click()")
  until("document.querySelectorAll('#calendar-sources input').length===1")
  ev("document.getElementById('setting-calendar-mode').value='icloud';document.getElementById('setting-language').value='en';document.getElementById('save-columns').click()")
  until("!document.getElementById('column-editor').open&&onlineState.records.length===6&&!onlineState.loading")
  assert ev("document.documentElement.lang==='en'&&document.getElementById('columns').textContent==='Settings'&&document.getElementById('month-title').textContent.includes('October')")
  assert ev("JSON.stringify(people.map(({id,name,color})=>({id,name,color})))===qaPeople&&JSON.stringify(events)===qaLocal")
  assert ev("calendarEvents().find(e=>e.title==='Bio').people.length===2")
  assert ev("document.querySelector('.holiday-name').textContent==='United Nations Day'")
  assert ev("document.querySelector('.date-number').textContent==='2026-10-01'")
  ev("document.getElementById('columns').click()")
  until("document.querySelector('.source-account')?.textContent.includes('test@example.invalid')")
  assert ev("document.querySelector('.source-account').textContent.startsWith('Connected as:')")
  ev("document.getElementById('cancel-columns').click()")
  # Add a generic CalDAV source via real browser and real CalDAV server.
  ev("document.getElementById('columns').click();document.getElementById('source-type').value='caldav';document.getElementById('source-type').dispatchEvent(new Event('change'));document.getElementById('source-name').value='Other calendar';document.getElementById('source-url').value="+json.dumps(dav_url)+";document.getElementById('source-user').value='calendar-user';document.getElementById('source-password').value='test-password';document.getElementById('connect-source').click()")
  until("onlineState.sources.length===2")
  assert ev("document.getElementById('source-password').value===''&&document.getElementById('source-url').value===''")
  # Only the extra source stays enabled; this also tests disabling primary iCloud.
  ev("document.querySelector('#calendar-sources input[data-source=\"icloud\"]').click();document.getElementById('save-columns').click()")
  until("!document.getElementById('column-editor').open&&!onlineState.loading&&onlineState.records.length===6")
  assert ev("onlineState.records.every(e=>e.sourceName==='Other calendar')")
  ev("document.getElementById('add').click()")
  assert ev("document.getElementById('editor-title').textContent==='New event'&&document.getElementById('event-source').value.startsWith('online:')")
  ev("""document.getElementById('title').value='Shared test';document.querySelectorAll('#person-options input').forEach(el=>el.checked=['person-5','person-4'].includes(el.value));document.getElementById('date').value='2026-10-28';document.getElementById('end-date').value='2026-10-28';document.getElementById('event-form').requestSubmit()""")
  until("!document.getElementById('editor').open&&!onlineState.loading&&onlineState.records.length===7")
  assert ev("calendarEvents().find(e=>e.title==='Shared test').people.length===2")
  ev("""document.querySelector('.cell[data-date="2026-10-28"][data-person="person-5"] .event').click();document.getElementById('title').value='Edited shared';document.getElementById('event-form').requestSubmit()""")
  until("!document.getElementById('editor').open&&!onlineState.loading&&calendarEvents().some(e=>e.title==='Edited shared')")
  # Switch language back through the actual settings save flow.
  ev("document.getElementById('columns').click();document.getElementById('setting-language').value='sv';document.getElementById('save-columns').click()")
  until("!document.getElementById('column-editor').open&&!onlineState.loading")
  assert ev("document.documentElement.lang==='sv'&&document.getElementById('columns').textContent==='Inställningar'&&document.querySelector('.holiday-name').textContent==='FN-dagen'")
  call('Page.reload');until("onlineState.records.length===7&&!onlineState.loading")
  assert ev("preferences.language==='sv'&&onlineState.sources.length===2&&people[0].name==='Gemensamt'")
  # Partial-source failure retains last records read-only.
  original_read=app_server.sources._read
  def fail_source(sid,s,c,first,last):
   if s['type']=='caldav':raise CalendarError('Testfel',502)
   return original_read(sid,s,c,first,last)
  app_server.sources._read=fail_source
  ev("refreshOnline(true)");until("!onlineState.loading&&onlineState.sourceErrors.length===1")
  assert ev("onlineState.records.length===7&&calendarEvents().every(e=>!e.writable)&&onlineState.records.every(e=>e.stale)")
  app_server.sources._read=original_read
  ev("refreshOnline(true)");until("!onlineState.loading&&!onlineState.error")
  # UI never stores server connection details or remote events in browser storage.
  assert ev("!JSON.stringify(localStorage).includes('test-password')&&!JSON.stringify(localStorage).includes('Edited shared')")
  ev("document.getElementById('columns').click();document.getElementById('source-type').value='google';document.getElementById('source-type').dispatchEvent(new Event('change'));document.getElementById('google-client-id').value='fixture.apps.googleusercontent.com';document.getElementById('google-client-secret').value='fixture-secret';document.getElementById('connect-source').click()")
  until("!document.getElementById('google-authorize').classList.contains('hidden')")
  assert ev("document.getElementById('google-client-secret').value===''&&new URL(document.getElementById('google-authorize').href).hostname==='accounts.google.com'")
  assert ev("!JSON.stringify(localStorage).includes('fixture-secret')")
  shot=call('Page.captureScreenshot',{'format':'png','captureBeyondViewport':False});(qa/'online-sources-settings.png').write_bytes(base64.b64decode(shot['data']))
  assert not errors,errors
  print('PASS: real browser + generic CalDAV CRUD, shared routing, iCloud preservation/disable, multiple sources, English/Swedish switching, ISO dates, holiday names, reload, partial failure and credential isolation; Google authorization UI.')
  call('Browser.close');proc.wait(timeout=15)
 finally:
  if proc.poll() is None:proc.terminate();proc.wait(timeout=15)

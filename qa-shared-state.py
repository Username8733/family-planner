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


  def until(code,evaluate=ev):
   for _ in range(200):
    if evaluate("typeof sharedSettings!=='undefined'&&("+code+")"):return
    time.sleep(.04)
   raise AssertionError('Timeout: '+code)
  seed={"version":3,"people":[{"id":"family","name":"Shared","initial":"SH","color":"#5e7359"}]+[{"id":"person-"+str(i),"name":"Person "+str(i),"initial":"P"+str(i),"color":color} for i,color in enumerate(['#2e6377','#936248','#5b729d','#906286','#927424'],1)],"events":[{"id":"local-picnic","title":"Local picnic","date":"2026-10-28","endDate":"2026-10-28","people":["family"],"time":"09:00","end":"10:00"}],"appearance":{"theme":"ios","mode":"light"},"preferences":{"language":"sv","timeFormat":"12h","temperatureUnit":"fahrenheit","weatherLocation":{"name":"Example City","latitude":0,"longitude":0},"temperatureSource":"weather","temperatureEntity":"","calendarMode":"mixed","onlineFallback":"family"},"touch":False}
  seed['people'][1]['name']='Alex'
  call('Page.addScriptToEvaluateOnNewDocument',{'source':"if(!localStorage.getItem('hemma-calendar-v1'))localStorage.setItem('hemma-calendar-v1',"+json.dumps(json.dumps(seed))+");"})
  call('Emulation.setDeviceMetricsOverride',{'width':1440,'height':1000,'deviceScaleFactor':1,'mobile':False})
  call('Page.navigate',{'url':app_url})
  until("sharedSettings.ready&&sharedSettings.revision>0&&!sharedSettings.inFlight&&onlineState.sources.length===1")
  until("!onlineState.loading&&onlineState.records.length===6")
  assert app_server.planner_state.get()['state']['people'][1]['name']=='Alex'
  assert app_server.planner_state.get()['state']['events'][0]['title']=='Local picnic'
  ev("document.getElementById('columns').click();document.getElementById('column-name-person-1').value='Jamie';document.getElementById('save-columns').click()")
  until("!document.getElementById('column-editor').open&&!sharedSettings.dirty&&!sharedSettings.inFlight")
  ev("document.getElementById('dark-mode').click();document.getElementById('touch').click()")
  until("!sharedSettings.dirty&&!sharedSettings.inFlight")
  # An incognito browser context has no shared localStorage or cookies.
  version=json.load(urllib.request.urlopen('http://127.0.0.1:'+port+'/json/version'))
  browser_ws=websocket.create_connection(version['webSocketDebuggerUrl'],suppress_origin=True,timeout=20)
  browser_seq=0
  def browser_call(method,params=None):
   global browser_seq
   browser_seq+=1;browser_ws.send(json.dumps({'id':browser_seq,'method':method,'params':params or {}}))
   while True:
    reply=json.loads(browser_ws.recv())
    if reply.get('id')==browser_seq:
     if 'error' in reply:raise RuntimeError(reply['error']['message'])
     return reply.get('result',{})
  context_id=browser_call('Target.createBrowserContext')['browserContextId']
  target=browser_call('Target.createTarget',{'url':'about:blank','browserContextId':context_id})['targetId']
  target_info=next(t for t in json.load(urllib.request.urlopen('http://127.0.0.1:'+port+'/json')) if t['id']==target)
  ws2=websocket.create_connection(target_info['webSocketDebuggerUrl'],suppress_origin=True,timeout=20)
  seq2=0
  def call2(method,params=None):
   global seq2
   seq2+=1;ws2.send(json.dumps({'id':seq2,'method':method,'params':params or {}}))
   while True:
    reply=json.loads(ws2.recv())
    if reply.get('method')=='Runtime.exceptionThrown':errors.append(reply['params']['exceptionDetails'].get('text','Runtime exception'))
    if reply.get('id')==seq2:
     if 'error' in reply:raise RuntimeError(reply['error']['message'])
     return reply.get('result',{})
  def ev2(code):
   result=call2('Runtime.evaluate',{'expression':code,'returnByValue':True,'awaitPromise':True})
   if result.get('exceptionDetails'):raise RuntimeError(str(result['exceptionDetails']))
   return result.get('result',{}).get('value')
  call2('Page.enable');call2('Runtime.enable')
  call2('Page.navigate',{'url':app_url})
  until("sharedSettings.ready&&onlineState.records.length===6&&!onlineState.loading",ev2)
  assert ev2("people[1].name==='Jamie'&&appearance.theme==='ios'&&appearance.mode==='dark'&&touch&&preferences.language==='sv'&&preferences.timeFormat==='12h'&&preferences.temperatureUnit==='fahrenheit'")
  assert ev2("preferences.weatherLocation.name==='Example City'&&preferences.calendarMode==='mixed'&&events.some(e=>e.title==='Local picnic')&&calendarEvents().length===7")
  assert ev2("!JSON.stringify(localStorage).includes('local-test-password')")
  # A change from the second device is picked up by the first device's polling path.
  ev2("document.getElementById('dark-mode').click()")
  until("!sharedSettings.dirty&&!sharedSettings.inFlight",ev2)
  ev("syncSharedState()")
  until("appearance.mode==='light'")
  revision=app_server.planner_state.get()['revision']
  call2('Page.reload')
  until("sharedSettings.ready&&!onlineState.loading&&onlineState.records.length===6",ev2)
  assert ev2("appearance.mode==='light'&&people[1].name==='Jamie'&&touch")
  assert app_server.planner_state.get()['revision']==revision
  assert not errors,errors
  print('PASS: existing browser settings and local events migrated once; a fresh isolated device receives columns, colors, theme/mode, language, time/unit, weather, larger rows and selected online calendar; cross-device updates, reload and credential isolation.')
  ws2.close();browser_call('Target.disposeBrowserContext',{'browserContextId':context_id})
  call('Browser.close');proc.wait(timeout=15)
 finally:
  if proc.poll() is None:proc.terminate();proc.wait(timeout=15)

import os
import sys,json,time,subprocess,tempfile,urllib.request,base64
from pathlib import Path
import websocket
root=Path(__file__).resolve().parent;qa=root/'qa';qa.mkdir(exist_ok=True)
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


  call('Page.navigate',{'url':(root/'dist/index.html').as_uri()});time.sleep(.3)
  assert ev("events.length===0&&people.length===6&&people.slice(1).map(p=>p.name).join(',')==='Person 1,Person 2,Person 3,Person 4,Person 5'")
  ev("""localStorage.removeItem(stateKey);localStorage.setItem('hemma-family-calendar-proposal-v2',JSON.stringify({people:[{id:'legacy',name:'Legacy test column',color:'#5e7359'}],events:[{title:'LEGACY_PRIVATE_MARKER',date:'2026-10-22',person:'legacy'}],preferences:{weatherLocation:{name:'Legacy location',latitude:1,longitude:1}}}));localStorage.setItem('hemma-family-calendar-proposal-v1','[{"title":"LEGACY_PRIVATE_MARKER"}]');localStorage.setItem('hemma-weather-old','LEGACY_WEATHER_MARKER')""")
  call('Page.reload');time.sleep(.3)
  assert ev("events.length===0&&people[1].name==='Person 1'&&preferences.weatherLocation===null&&preferences.calendarMode==='local'")
  assert ev("!localStorage.getItem('hemma-family-calendar-proposal-v1')&&!localStorage.getItem('hemma-family-calendar-proposal-v2')&&!localStorage.getItem('hemma-weather-old')")
  assert ev("document.querySelectorAll('.event').length===0&&document.querySelectorAll('#people th').length===7")
  ev("""events.push({id:'new-test',title:'New local activity',date:key(month),endDate:key(month),people:['person-1'],time:'',end:''});persist()""")
  call('Page.reload');time.sleep(.3)
  assert ev("events.length===1&&events[0].title==='New local activity'")
  ev("window.confirm=()=>true;document.getElementById('reset').click()")
  assert ev("events.length===0&&people[1].name==='Person 1'&&document.querySelectorAll('.event').length===0")
  ev("document.getElementById('columns').click();document.getElementById('setting-language').value='en';document.getElementById('save-columns').click()")
  assert ev("preferences.language==='en'&&events.length===0&&document.getElementById('reset').textContent==='Reset calendar'")
  assert not errors,errors
  print('PASS: empty generic template, removal of legacy activity/location data, no sample events, new data preserved on reload, clean reset and English labels.')
  call('Browser.close');proc.wait(timeout=15)
 finally:
  if proc.poll() is None:proc.terminate();proc.wait(timeout=15)

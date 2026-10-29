"""Isolated browser check of read-first event details; never connects to calendars."""
import base64,json,os,pathlib,subprocess,tempfile,threading,time,urllib.request
from functools import partial
from http.server import ThreadingHTTPServer,SimpleHTTPRequestHandler
import websocket
root=pathlib.Path(__file__).resolve().parent
class QuietHandler(SimpleHTTPRequestHandler):
 def log_message(self,*args):pass
server=ThreadingHTTPServer(('127.0.0.1',0),partial(QuietHandler,directory=str(root/'dist')))
threading.Thread(target=server.serve_forever,daemon=True).start()
with tempfile.TemporaryDirectory(prefix='planner-overview-') as profile:
 browser=subprocess.Popen([os.environ.get('BRAVE_BINARY','/Applications/Brave Browser.app/Contents/MacOS/Brave Browser'),'--headless','--disable-extensions','--disable-gpu','--no-first-run','--no-proxy-server','--remote-debugging-address=127.0.0.1','--remote-debugging-port=0','--user-data-dir='+profile,'about:blank'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 try:
  portfile=pathlib.Path(profile)/'DevToolsActivePort'
  for _ in range(150):
   if portfile.exists():break
   time.sleep(.1)
  port=portfile.read_text().splitlines()[0]
  pages=json.load(urllib.request.urlopen('http://127.0.0.1:'+port+'/json/list'));page=next(p for p in pages if p['type']=='page')
  socket=websocket.create_connection(page['webSocketDebuggerUrl'],suppress_origin=True);seq=0;errors=[]
  def call(method,params={}):
   global seq
   seq+=1;socket.send(json.dumps({'id':seq,'method':method,'params':params}))
   while True:
    result=json.loads(socket.recv())
    if result.get('method')=='Runtime.exceptionThrown':errors.append(result['params'])
    if result.get('id')==seq:
     assert 'error' not in result,result
     return result.get('result',{})
  def ev(code):
   r=call('Runtime.evaluate',{'expression':code,'returnByValue':True,'awaitPromise':True});assert 'exceptionDetails' not in r,r
   return r.get('result',{}).get('value')
  call('Runtime.enable');call('Page.enable');call('Emulation.setDeviceMetricsOverride',{'width':1280,'height':900,'deviceScaleFactor':1,'mobile':False});call('Page.navigate',{'url':f'http://127.0.0.1:{server.server_port}/'})
  for _ in range(100):
   time.sleep(.1)
   if ev('typeof editEvent==="function"'):break
  ev('setLanguage("sv");applyStaticLanguage();window.qaEvent={id:"qa-no-save",title:"Familjemiddag",date:"2026-10-29",endDate:"2026-10-30",time:"18:00",end:"20:00",people:plannerSnapshot().people.slice(0,2).map(p=>p.id),location:"Hemma",description:"Ta med efterrätt.\\nSamling i köket. <img src=x onerror=window.qaUnsafe=true>"};openEvent(qaEvent,qaEvent.date,qaEvent.people[0])')
  assert ev('document.getElementById("event-overview").open&&!document.getElementById("editor").open&&!window.qaUnsafe')
  assert ev('document.getElementById("overview-time").textContent==="18:00 – 20:00"&&document.querySelectorAll("#overview-people span").length===2&&document.getElementById("overview-notes").textContent.includes("efterrätt")&&document.getElementById("overview-edit").textContent==="Ändra"')
  ev('document.getElementById("overview-edit").click()');assert ev('!document.getElementById("event-overview").open&&document.getElementById("editor").open&&document.getElementById("title").value==="Familjemiddag"');ev('document.getElementById("close").click()');time.sleep(.05)
  for writable,can_update in [(False,True),(True,False)]:
   ev('openEvent({...qaEvent,online:true,writable:'+json.dumps(writable)+',onlineRecord:{canUpdate:'+json.dumps(can_update)+'}},qaEvent.date,qaEvent.people[0]);document.getElementById("overview-edit").click()');assert ev('document.getElementById("overview-edit").disabled&&!document.getElementById("editor").open');ev('document.getElementById("overview-back").click()');time.sleep(.05)
  ev('openEvent({...qaEvent,online:true,writable:true,onlineRecord:{canUpdate:true,editEndDate:"2026-10-30",editEndTime:"21:30",calendarName:"Familj"}},qaEvent.date,qaEvent.people[0])');assert ev('!document.getElementById("overview-edit").disabled&&document.getElementById("overview-time").textContent.endsWith("21:30")');ev('document.getElementById("overview-edit").click()');assert ev('document.getElementById("editor").open');ev('document.getElementById("close").click()');time.sleep(.05)
  ev('openCell("2026-10-29",plannerSnapshot().people[0].id)');assert ev('document.getElementById("editor").open&&!document.getElementById("event-overview").open');ev('document.getElementById("close").click()');time.sleep(.05)
  call('Emulation.setDeviceMetricsOverride',{'width':390,'height':844,'deviceScaleFactor':1,'mobile':False})
  ev('openEvent({...qaEvent,time:"",end:"",endDate:qaEvent.date,description:"Lång anteckning. ".repeat(900)},qaEvent.date,qaEvent.people[0])');assert ev('document.getElementById("overview-time").textContent==="Hela dagen"&&document.getElementById("event-overview").getBoundingClientRect().width<=390&&document.getElementById("overview-edit").getBoundingClientRect().bottom<844')
  call('Input.dispatchKeyEvent',{'type':'keyDown','key':'Escape','code':'Escape','windowsVirtualKeyCode':27});call('Input.dispatchKeyEvent',{'type':'keyUp','key':'Escape','code':'Escape','windowsVirtualKeyCode':27});time.sleep(.05);assert ev('!document.getElementById("event-overview").open')
  ev('setLanguage("en");applyStaticLanguage();openEvent({...qaEvent,time:"",end:""},qaEvent.date,qaEvent.people[0])');assert ev('document.getElementById("overview-time").textContent==="All day"&&document.getElementById("overview-edit").textContent==="Edit"')
  assert not errors,errors
  print('PASS: read-first overview, explicit editing, notes/people/times, provider capabilities, new event, mobile long notes, Escape, English/Swedish, safe text rendering; no calendar writes.')
 finally:
  browser.terminate()
  try:browser.wait(timeout=10)
  except subprocess.TimeoutExpired:browser.kill();browser.wait()
  server.shutdown();server.server_close()

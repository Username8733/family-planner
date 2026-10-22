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

  from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
  from urllib.parse import urlsplit,parse_qs
  import threading
  callbacks=[]
  class Fixture(BaseHTTPRequestHandler):
   def log_message(self,*args):pass
   def do_GET(self):
    path=urlsplit(self.path).path
    if path=='/adapter.js':
     data=(root/'dist/hemma-calendar-card.js').read_bytes();ctype='text/javascript; charset=utf-8'
    elif path.endswith('/api/oauth/google/callback'):
     callbacks.append(parse_qs(urlsplit(self.path).query));data=b'OK';ctype='text/plain'
    elif path.startswith('/api/hassio_ingress/'):
     data=b"""<script>addEventListener('message',e=>parent.postMessage({type:'fixture-received',value:e.data},location.origin));parent.postMessage({type:'hemma-temperature-ready-v1'},location.origin)</script>""";ctype='text/html'
    else:
     data=b'<html><meta charset="utf-8"><body><script src="/adapter.js"></script></body></html>';ctype='text/html'
    self.send_response(200);self.send_header('Content-Type',ctype);self.end_headers();self.wfile.write(data)
  fixture=ThreadingHTTPServer(('127.0.0.1',0),Fixture)
  threading.Thread(target=fixture.serve_forever,daemon=True).start()
  call('Page.navigate',{'url':'http://127.0.0.1:'+str(fixture.server_port)+'/dashboard-family-planner/calendar?state=fixture-state&code=fixture-code'});time.sleep(.15)
  ev("""window.wsCalls=[];window.received=[];addEventListener('message',e=>{if(e.data?.type==='fixture-received')received.push(e.data.value)});
   window.adapter=document.createElement('hemma-calendar-card');document.body.append(adapter);
   adapter.setConfig({url:'/api/hassio_ingress/fixture/index.html'});
   adapter.hass={states:{'sensor.outdoor':{entity_id:'sensor.outdoor',state:'12.3',last_updated:'2026-10-22T10:00:00Z',attributes:{device_class:'temperature',unit_of_measurement:'°C',friendly_name:'Outside'}},'light.private':{entity_id:'light.private',state:'on',attributes:{}}},callWS:async command=>{wsCalls.push(command);return command.endpoint==='/ingress/session'?{session:'fixture-session'}:{}}};
  """)
  for _ in range(50):
   if ev("adapter.ingressReady&&received.some(m=>m.sensors?.length===1)"):break
   time.sleep(.03)
  assert ev("adapter.ingressReady"),ev("({ready:adapter.ingressReady,pending:adapter.ingressPending,status:adapter.status?.textContent,cookie:document.cookie,calls:wsCalls,source:adapter.frame.src})")
  assert callbacks==[{'state':['fixture-state'],'code':['fixture-code']}],callbacks
  assert ev("!location.search.includes('code=')&&!location.search.includes('state=')")
  assert ev("received.some(m=>m.type==='hemma-temperature-states-v1'&&m.sensors.length===1&&m.sensors[0].id==='sensor.outdoor')"),ev("received")
  assert ev("!JSON.stringify(received).includes('light.private')")
  # Periodic validation, then a failed session triggers fresh authentication.
  ev("adapter.keepIngressAlive()")
  assert ev("wsCalls.some(c=>c.endpoint==='/ingress/validate_session'&&c.data.session==='fixture-session')")
  ev("""adapter._hass.callWS=async command=>{wsCalls.push(command);if(command.endpoint==='/ingress/validate_session')throw Error('expired');return {session:'fixture-renewed'}};adapter.keepIngressAlive()""")
  assert ev("adapter.ingressReady&&adapter.ingressSession==='fixture-renewed'")
  assert len(callbacks)==1
  assert ev("(()=>{try{adapter.setConfig({url:'https://untrusted.example/calendar'});return false}catch{return true}})()")
  # Failed initialization exposes a retry control without loading an unauthenticated frame.
  ev("""adapter.remove();window.retryCard=document.createElement('hemma-calendar-card');document.body.append(retryCard);retryCard.setConfig({url:'/api/hassio_ingress/fixture/index.html'});retryCard.hass={states:{},callWS:async()=>{throw Error('offline')}}""")
  assert ev("!!retryCard.status&&!retryCard.ingressReady")
  ev("retryCard._hass.callWS=async()=>({session:'fixture-retry'});retryCard.status.click()")
  assert ev("retryCard.ingressReady&&!retryCard.status.isConnected")
  assert not errors,errors
  fixture.shutdown();fixture.server_close()
  print('PASS: HA ingress session creation and cookie, protected OAuth callback forwarding with history cleanup, temperature-only messages, session validation/renewal, origin rejection and retry after failure.')
  call('Browser.close');proc.wait(timeout=15)
 finally:
  if proc.poll() is None:proc.terminate();proc.wait(timeout=15)

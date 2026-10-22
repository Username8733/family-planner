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

  call('Emulation.setDeviceMetricsOverride',{'width':1440,'height':1000,'deviceScaleFactor':1,'mobile':False})
  call('Page.navigate',{'url':(root/'dist/index.html').as_uri()});time.sleep(.1)
  ev('month=new Date(2026,9,1);events=[\n    {id:\'tone-a\',title:"Autumn trip",date:\'2026-10-22\',endDate:\'2026-10-26\',people:[\'family\'],time:\'\',end:\'\'},\n    {id:\'tone-b\',title:"Family visit",date:\'2026-10-23\',endDate:\'2026-10-25\',people:[\'family\'],time:\'\',end:\'\'},\n    {id:\'tone-shared\',title:\'Gemensamma planer\',date:\'2026-10-24\',endDate:\'2026-10-27\',people:[\'person-1\',\'person-2\'],time:\'\',end:\'\'},\n    {id:\'single\',title:\'Enskild aktivitet\',date:\'2026-10-23\',endDate:\'2026-10-23\',people:[\'family\'],time:\'18:00\',end:\'\'}\n  ];render();\n  window.qaContrast=el=>{\n   const ctx=document.createElement(\'canvas\').getContext(\'2d\');\n   const rgb=value=>{ctx.clearRect(0,0,1,1);ctx.fillStyle=value;ctx.fillRect(0,0,1,1);return [...ctx.getImageData(0,0,1,1).data].slice(0,3)};\n   const lum=c=>c.map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4}).reduce((s,v,i)=>s+v*[.2126,.7152,.0722][i],0);\n   const style=getComputedStyle(el),a=lum(rgb(style.color)),b=lum(rgb(style.backgroundColor));return (Math.max(a,b)+.05)/(Math.min(a,b)+.05);\n  }')
  for theme in ['home','sage','ocean','sand','plum','start']:
   for mode in ['light','dark']:
    ev("appearance={theme:"+json.dumps(theme)+",mode:"+json.dumps(mode)+"};applyAppearance()")
    assert ev("""['tone-a','tone-b','tone-shared'].every(id=>new Set([...document.querySelectorAll('[data-event-id="'+id+'"]')].map(el=>getComputedStyle(el).backgroundColor)).size===1)""")
    assert ev("""getComputedStyle(document.querySelector('[data-event-id="tone-a"]')).backgroundColor!==getComputedStyle(document.querySelector('[data-event-id="tone-b"]')).backgroundColor""")
    ratios=ev("""[...document.querySelectorAll('.event.range')].map(qaContrast)""")
    assert min(ratios)>=4.5,str((theme,mode,min(ratios)))
    assert ev("document.querySelectorAll('[data-event-id=\"tone-a\"] .event-title').length===1&&document.querySelectorAll('[data-event-id=\"tone-shared\"] .event-title').length===1")
    assert ev("parseFloat(getComputedStyle(document.querySelector('.range-middle')).borderTopLeftRadius)===0"),str((theme,mode,ev("getComputedStyle(document.querySelector('.range-middle')).borderTopLeftRadius")))
    if theme=='start':
     shot=call('Page.captureScreenshot',{'format':'png','captureBeyondViewport':False});(qa/('range-colors-'+mode+'.png')).write_bytes(base64.b64decode(shot['data']))
  assert not errors,errors
  print('PASS: stable color across days and shared participants; subtle differences per multi-day event; contrast >=4.5 in all 12 theme variants; continuous band corners and single title retained.')
  call('Browser.close');proc.wait(timeout=15)
 finally:
  if proc.poll() is None:proc.terminate();proc.wait(timeout=15)

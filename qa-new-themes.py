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

  call('Page.navigate',{'url':(root/'dist/index.html').as_uri()});time.sleep(.4)
  ev("""month=new Date(2026,9,1);events=[
   {id:'ink-single',title:'Tandläkare',date:'2026-10-22',endDate:'2026-10-22',people:['person-1'],time:'09:00',end:'10:00'},
   {id:'ink-shared',title:'Familjemiddag',date:'2026-10-23',endDate:'2026-10-23',people:['person-1','person-2'],time:'18:00',end:''},
   {id:'ink-range',title:'Höstlov',date:'2026-10-24',endDate:'2026-10-28',people:['person-5'],time:'',end:''}
  ];render()""")
  assert ev("['eink','ios'].every(id=>[...document.getElementById('visual-theme').options].some(o=>o.value===id))")
  for label,w,h in [('desktop',1440,1000),('ipad',768,1024),('ipad-landscape',1024,768)]:
   call('Emulation.setDeviceMetricsOverride',{'width':w,'height':h,'deviceScaleFactor':1,'mobile':False})
   for theme in ['eink','ios']:
    for mode in ['light','dark']:
     ev("document.getElementById('visual-theme').value="+json.dumps(theme)+";document.getElementById('visual-theme').dispatchEvent(new Event('change'));")
     if ev('appearance.mode')!=mode:ev("document.getElementById('dark-mode').click()")
     time.sleep(.1)
     d=ev("""(()=>{const c=document.getElementById('calendar'),e=document.querySelector('[data-event-id="ink-single"]'),s=document.querySelector('[data-event-id="ink-shared"]'),a=getComputedStyle(e),b=getComputedStyle(s);return {height:c.clientHeight,content:c.scrollHeight,page:document.documentElement.scrollWidth,viewport:innerWidth,eventColor:a.color,eventBg:a.backgroundColor,sharedBorder:b.borderLeftStyle,transition:a.transitionDuration,shadow:a.boxShadow,filter:a.filter,theme:document.documentElement.dataset.theme,mode:document.documentElement.dataset.mode}})()""")
     assert d['theme']==theme and d['mode']==mode,d
     assert d['content']<=d['height']+1,(label,d)
     assert d['page']<=d['viewport'],(label,d)
     assert d['eventColor']!=d['eventBg'],d
     if theme=='eink':
      assert d['sharedBorder']=='dashed' and d['shadow']=='none' and d['transition']=='0s' and d['filter']=='none',d
      assert d['eventColor']==('rgb(0, 0, 0)' if mode=='light' else 'rgb(255, 255, 255)'),d
     shot=call('Page.captureScreenshot',{'format':'png','captureBeyondViewport':False});(qa/('theme-'+theme+'-'+mode+'-'+label+'.png')).write_bytes(base64.b64decode(shot['data']))
  # Persisted theme must survive the early page initialization as well.
  call('Page.reload');time.sleep(.35)
  assert ev("appearance.theme==='ios'&&appearance.mode==='dark'&&document.documentElement.dataset.theme==='ios'")
  ev("document.querySelector('.event').click()")
  assert ev("document.getElementById('editor').open")
  ev("document.getElementById('close').click()")
  assert not errors,errors
  print('PASS: two new themes, both modes, desktop/iPad layouts, full month fit, monochrome contrast and shared outlines, persistence and event editing.')
  call('Browser.close');proc.wait(timeout=15)
 finally:
  if proc.poll() is None:proc.terminate();proc.wait(timeout=15)

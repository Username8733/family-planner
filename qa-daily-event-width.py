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

  call('Page.navigate',{'url':(root/'dist/index.html').as_uri()});time.sleep(.15)
  ev('month=new Date(2026,9,1);events=[\n   {id:\'range-a\',title:"Long event",date:\'2026-10-22\',endDate:\'2026-10-25\',people:[\'family\'],time:\'\',end:\'\'},\n   {id:\'range-b\',title:"Shared event",date:\'2026-10-23\',endDate:\'2026-10-24\',people:[\'family\',\'person-1\'],time:\'\',end:\'\'},\n   {id:\'short-c\',title:"Short event",date:\'2026-10-23\',endDate:\'2026-10-23\',people:[\'family\'],time:\'\',end:\'\'},\n   {id:\'short-d\',title:"Extra event",date:\'2026-10-23\',endDate:\'2026-10-23\',people:[\'family\'],time:\'\',end:\'\'},\n   {id:\'first-hole\',title:"Short opening event",date:\'2026-10-22\',endDate:\'2026-10-22\',people:[\'person-2\'],time:\'\',end:\'\'},\n   {id:\'second-lane\',title:"Across the month boundary",date:\'2026-10-22\',endDate:\'2026-11-02\',people:[\'person-2\'],time:\'23:00\',end:\'08:00\'}\n  ];render()')
  for label,w,h in [('desktop',1440,1000),('ipad',768,1024)]:
   call('Emulation.setDeviceMetricsOverride',{'width':w,'height':h,'deviceScaleFactor':1,'mobile':False});time.sleep(.1)
   for theme in ['home','start']:
    for mode in ['light','dark']:
     ev("appearance={theme:"+json.dumps(theme)+",mode:"+json.dumps(mode)+"};applyAppearance()");time.sleep(.03)
     for person,day,count in [('family','2026-10-23',4),('family','2026-10-24',2),('family','2026-10-25',1),('person-1','2026-10-24',1),('person-2','2026-10-24',1),('person-5','2026-10-24',0)]:
      dims=ev("""(()=>{const cell=document.querySelector('.cell[data-date="%s"][data-person="%s"]'),style=getComputedStyle(cell),buttons=[...cell.querySelectorAll('.event')];return {count:buttons.length,empty:cell.querySelectorAll('.empty-slot').length,lanes:Number(style.getPropertyValue('--lanes')),crowded:cell.classList.contains('crowded'),width:cell.clientWidth,leftPad:parseFloat(style.paddingLeft),rightPad:parseFloat(style.paddingRight),gap:parseFloat(style.columnGap),rects:buttons.map(b=>{const r=b.getBoundingClientRect();return {width:r.width,y:r.y}})}})()"""%(day,person))
      assert dims['count']==count and dims['lanes']==max(1,count),str((person,day,dims))
      assert dims['empty']==(1 if count==0 else 0),str((person,day,dims))
      assert dims['crowded']==(count>3),str((person,day,dims))
      if 0<count<=3:
       expected=(dims['width']-dims['leftPad']-dims['rightPad']-(count-1)*dims['gap'])/count
       assert all(abs(r['width']-expected)<1 for r in dims['rects']),str((person,day,dims,expected))
       assert max(r['y'] for r in dims['rects'])-min(r['y'] for r in dims['rects'])<1
  # Multi-day titles, shared membership and editing still operate on the original event.
  assert ev("document.querySelectorAll('[data-event-id=\"range-a\"] .event-title').length===1")
  assert ev("document.querySelectorAll('[data-event-id=\"range-b\"].shared').length===4")
  ev('document.querySelector(\'.cell[data-person="family"][data-date="2026-10-24"] [data-event-id="range-b"]\').click();document.getElementById(\'title\').value="Updated shared event";document.getElementById(\'event-form\').requestSubmit()')
  assert ev("events.find(e=>e.id==='range-b').people.length===2&&document.querySelectorAll('[data-event-id=\"range-b\"]').length===4")
  ev("month=new Date(2026,10,1);render()")
  assert ev('(()=>{const c=document.querySelector(\'.cell[data-date="2026-11-01"][data-person="person-2"]\');return c.querySelectorAll(\'.event\').length===1&&c.style.getPropertyValue(\'--lanes\')===\'1\'&&c.querySelector(\'.event-title\').textContent==="Across the month boundary"})()')
  assert not errors,errors
  print('PASS: widths fill each day for 1/2 events after a 4-event peak; no reserved empty lanes; crowded state per day; empty day remains clickable; shared and multiday editing, labels and month boundaries preserved in both modes and screen sizes.')
  call('Browser.close');proc.wait(timeout=15)
 finally:
  if proc.poll() is None:proc.terminate();proc.wait(timeout=15)

import os
import sys,json,time,subprocess,tempfile,urllib.request,base64
from pathlib import Path
import websocket
root=Path(__file__).resolve().parent;qa=root/'qa';qa.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory(prefix='browser-',dir=qa) as temp:
 proc=subprocess.Popen([os.environ.get('BRAVE_BINARY','/Applications/Brave Browser.app/Contents/MacOS/Brave Browser'),'--headless','--disable-extensions','--disable-gpu','--no-first-run','--disable-background-networking','--remote-debugging-address=127.0.0.1','--remote-debugging-port=0','--user-data-dir='+temp,'about:blank'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 try:
  for _ in range(100):
   f=Path(temp)/'DevToolsActivePort'
   if f.exists() and f.read_text().strip():break
   time.sleep(.1)
  port=f.read_text().splitlines()[0]
  targets=json.load(urllib.request.urlopen('http://127.0.0.1:'+port+'/json',timeout=4))
  ws=websocket.create_connection(next(t for t in targets if t.get('type')=='page')['webSocketDebuggerUrl'],suppress_origin=True,timeout=60);seq=0;errors=[];network=[]
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

  call('Page.navigate',{'url':(root/'dist/index.html').as_uri()});time.sleep(.2)
  for _ in range(150):
   if ev('typeof render==="function"'):break
   time.sleep(.1)
  assert ev('typeof render==="function"'),ev('({url:location.href,title:document.title,body:document.body.innerText.slice(0,500)})')
  ev("""month=new Date(2026,9,1);events=[
   {id:'range-a',title:'Long event',date:'2026-10-22',endDate:'2026-10-25',people:['family'],time:'',end:''},
   {id:'range-b',title:'Shared event',date:'2026-10-23',endDate:'2026-10-24',people:['family','person-1'],time:'',end:''},
   {id:'short-c',title:'Short event',date:'2026-10-23',people:['family'],time:'',end:''},
   {id:'short-d',title:'Extra event',date:'2026-10-23',people:['family'],time:'',end:''},
   {id:'first-hole',title:'Short opening event',date:'2026-10-22',people:['person-2'],time:'',end:''},
   {id:'second-lane',title:'Across the month boundary',date:'2026-10-22',endDate:'2026-11-02',people:['person-2'],time:'23:00',end:'08:00'},
   {id:'unrelated',title:'Independent event',date:'2026-10-28',people:['family'],time:'',end:''}
  ];render()""")
  for label,w,h in [('desktop',1440,1000),('ipad',768,1024),('landscape',1024,768),('phone',390,844)]:
   call('Emulation.setDeviceMetricsOverride',{'width':w,'height':h,'deviceScaleFactor':1,'mobile':False});time.sleep(.1)
   for theme in ['home','start','eink','ios']:
    for mode in ['light','dark']:
     ev("appearance={theme:"+json.dumps(theme)+",mode:"+json.dumps(mode)+"};applyAppearance()");time.sleep(.02)
     dims=ev("""(()=>{return ['22','23','24','25'].map(d=>{const c=document.querySelector('.cell[data-date="2026-10-'+d+'"][data-person="family"]'),b=c.querySelector('[data-event-id="range-a"]'),r=b.getBoundingClientRect(),cr=c.getBoundingClientRect();return {width:r.width,x:r.x-cr.x,scroll:c.scrollWidth>c.clientWidth+1,lanes:+c.style.getPropertyValue('--lanes')}})})()""")
     assert max(d['width'] for d in dims)-min(d['width'] for d in dims)<1,str(dims)
     assert max(d['x'] for d in dims)-min(d['x'] for d in dims)<1,str(dims)
     assert all(d['lanes']==3 and not d['scroll'] for d in dims),str(dims)
     assert ev("""(()=>{const cells=['22','24','25'].map(d=>document.querySelector('.cell[data-date="2026-10-'+d+'"][data-person="family"]'));return cells.every(c=>!c.querySelector('.cell-add')&&c.querySelector('.empty-slot'))&&!!document.querySelector('.cell[data-date="2026-10-23"][data-person="family"] .cell-add')})()""")
     assert ev("""(()=>{const c=document.querySelector('.cell[data-date="2026-10-23"][data-person="family"]');return c.querySelectorAll('.event').length===2&&c.querySelector('.more-events').textContent==='+2'})()""")
     assert ev("""document.querySelector('.cell[data-date="2026-10-28"][data-person="family"]').style.getPropertyValue('--lanes')==='1'""")
     # Open the whole day from the dense cell; the shared event appears once.
     ev("""document.querySelector('.cell[data-date="2026-10-23"][data-person="family"] .more-events').click()""")
     detail=ev("""(()=>{const d=document.getElementById('day-detail');return {open:d.open,scroll:d.scrollHeight>d.clientHeight+1,cards:[...d.querySelectorAll('.day-event')].map(b=>b.dataset.eventId),page:document.getElementById('day-page').textContent,bounds:d.getBoundingClientRect().toJSON()}})()""")
     assert detail['open'] and not detail['scroll'],str((label,theme,mode,detail))
     assert detail['bounds']['top']>=0 and detail['bounds']['bottom']<=h+1,str(detail)
     seen=detail['cards']
     while ev("!document.getElementById('day-next').disabled"):
      ev("document.getElementById('day-next').click()")
      seen+=ev("[...document.querySelectorAll('#day-events .day-event')].map(b=>b.dataset.eventId)")
     assert len(seen)==5 and len(set(seen))==5,str(seen)
     ev("document.getElementById('close-day').click()")
  # Date buttons and event buttons in dense cells open the day view.
  ev("""document.querySelector('.cell[data-date="2026-10-23"][data-person="family"] .event').click()""")
  assert ev("document.getElementById('day-detail').open&&!document.getElementById('editor').open")
  ev("document.getElementById('close-day').click();document.querySelectorAll('.day-open')[22].click()")
  assert ev("document.getElementById('day-title').textContent==='2026-10-23'")
  # Edit a shared event from the day view, preserving participants and updating its cards.
  ev("detailPage=0;renderDay()")
  while not ev("!!document.querySelector('#day-events [data-event-id=\"range-b\"]')"):
   ev("document.getElementById('day-next').click()")
  ev("""document.querySelector('#day-events [data-event-id="range-b"]').click();document.getElementById('overview-edit').click();document.getElementById('title').value='Updated shared event';document.getElementById('event-form').requestSubmit()""")
  assert ev("events.find(e=>e.id==='range-b').people.length===2&&document.getElementById('day-detail').open&&!document.getElementById('editor').open")
  ev("detailPage=0;renderDay()")
  while not ev("!!document.querySelector('#day-events [data-event-id=range-b]')"):
   ev("document.getElementById('day-next').click()")
  assert ev("document.querySelector('#day-events [data-event-id=range-b] strong').textContent==='Updated shared event'")
  ev("document.getElementById('day-add').click()")
  assert ev("document.getElementById('editor').open&&document.getElementById('date').value==='2026-10-23'")
  ev("document.getElementById('close').click();document.getElementById('close-day').click()")
  # Stable lane positions survive the month boundary.
  ev("month=new Date(2026,10,1);render()")
  assert ev("""(()=>{const c=document.querySelector('.cell[data-date="2026-11-01"][data-person="person-2"]');return c.style.getPropertyValue('--lanes')==='2'&&c.querySelector('[data-event-id="second-lane"]').dataset.lane==='1'&&c.querySelector('.event-title').textContent==='Across the month boundary'})()""")
  # Empty days, localized text, and a large collection with no nested scrolling.
  ev("setLanguage('sv');applyStaticLanguage();openDay('2026-11-15')")
  assert ev("document.querySelector('.day-empty').textContent==='Inga aktiviteter den här dagen.'")
  ev("""document.getElementById('close-day').click();setLanguage('en');applyStaticLanguage();month=new Date(2026,9,1);events=Array.from({length:25},(_,i)=>({id:'busy-'+i,title:'Busy day activity '+(i+1),date:'2026-10-24',people:['family'],time:'12:00',end:'13:00'}));render();openDay('2026-10-24')""")
  seen=[]
  while True:
   detail=ev("""(()=>{const d=document.getElementById('day-detail');return {scroll:d.scrollHeight>d.clientHeight+1,ids:[...d.querySelectorAll('.day-event')].map(b=>b.dataset.eventId),last:document.getElementById('day-next').disabled}})()""")
   assert not detail['scroll'],str(detail)
   seen+=detail['ids']
   if detail['last']:break
   ev("document.getElementById('day-next').click()")
  assert len(seen)==25 and len(set(seen))==25,str(seen)
  call('Emulation.setDeviceMetricsOverride',{'width':1440,'height':1000,'deviceScaleFactor':1,'mobile':False});time.sleep(.1)
  ev("detailPage=0;renderDay()")
  shot=call('Page.captureScreenshot',{'format':'png'})
  (qa/'day-detail.png').write_bytes(base64.b64decode(shot['data']))
  assert not errors,errors
  print('PASS: stable range widths and positions, month boundary lanes, compact overflow, no horizontal cell scrolling; paged full-day view, unique shared events, editing, adding, empty dates and Swedish text; desktop/tablet/phone, four themes and both modes; all 25 events reachable.')
  call('Browser.close');proc.wait(timeout=15)
 finally:
  if proc.poll() is None:proc.terminate();proc.wait(timeout=15)

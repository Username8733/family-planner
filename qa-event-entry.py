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

  call('Page.navigate',{'url':(root/'dist/index.html').as_uri()});time.sleep(.2)
  ev("""month=new Date(2026,9,1);events=[
    {id:'occupied',title:'Already planned',date:'2026-10-24',people:['family'],time:'09:00',end:'10:00'},
    ...Array.from({length:5},(_,i)=>({id:'dense-'+i,title:'Dense activity '+i,date:'2026-10-25',people:['person-1'],time:'12:00',end:'13:00'}))
   ];render()""")
  call('Emulation.setDeviceMetricsOverride',{'width':1440,'height':1000,'deviceScaleFactor':1,'mobile':False});time.sleep(.1)
  # Plus is a separate hit target on both occupied and crowded cells.
  for person,day in [('family','2026-10-24'),('person-1','2026-10-25')]:
   hit=ev("""(()=>{const b=document.querySelector('.cell[data-date="%s"][data-person="%s"] .cell-add'),r=b.getBoundingClientRect();return {hit:document.elementFromPoint(r.x+r.width/2,r.y+r.height/2)===b,width:r.width,height:r.height}})()"""%(day,person))
   assert hit['hit'] and hit['width']>=20 and hit['height']>8,str(hit)
   ev("""document.querySelector('.cell[data-date="%s"][data-person="%s"] .cell-add').click()"""%(day,person))
   assert ev("document.getElementById('editor').open&&!document.getElementById('day-detail').open&&document.getElementById('date').value==='"+day+"'&&selectedPeople().includes('"+person+"')&&!editing")
   ev("document.getElementById('close').click()")
  # Icon buttons and AM/PM fit beside the editable fields in every theme.
  for label,w,h in [('desktop',1440,1000),('ipad',768,1024),('phone',390,844)]:
   call('Emulation.setDeviceMetricsOverride',{'width':w,'height':h,'deviceScaleFactor':1,'mobile':False});time.sleep(.05)
   for theme in ['home','sage','ocean','sand','plum','start','eink','ios']:
    for mode in ['light','dark']:
     for fmt in ['24h','12h']:
      ev("preferences.timeFormat="+json.dumps(fmt)+";applyTimePreferences();appearance={theme:"+json.dumps(theme)+",mode:"+json.dumps(mode)+"};applyAppearance();openCell('2026-10-24','family')")
      dims=ev("""(()=>{return [...document.querySelectorAll('#event-form .input-picker')].map(p=>{const i=p.querySelector('input'),b=p.querySelector('.picker-trigger'),period=p.querySelector('select:not(.hidden)'),ir=i.getBoundingClientRect(),br=b.getBoundingClientRect(),pr=period?.getBoundingClientRect(),r=p.getBoundingClientRect();return {width:ir.width,noOverlap:ir.right<=(pr?.left??br.left),fits:br.right<=r.right+1,icon:!!b.querySelector('svg'),text:b.textContent.trim(),scroll:p.scrollWidth>p.clientWidth+1}})})()""")
      assert all(d['width']>=65 and d['noOverlap'] and d['fits'] and d['icon'] and not d['text'] and not d['scroll'] for d in dims),str((label,theme,mode,fmt,dims))
      if theme=='start' and mode=='light' and fmt=='12h' and label in ['desktop','phone']:
       shot=call('Page.captureScreenshot',{'format':'png','captureBeyondViewport':False})
       (qa/('event-entry-'+label+'.png')).write_bytes(base64.b64decode(shot['data']))
      ev("document.getElementById('close').click()")
  ev("preferences.timeFormat='24h';applyTimePreferences()")
  def start(value):
   ev("document.getElementById('time').value="+json.dumps(value)+";document.getElementById('time').dispatchEvent(new InputEvent('input',{bubbles:true,inputType:'insertText'}))")
  def end(value):
   ev("document.getElementById('end').value="+json.dumps(value)+";document.getElementById('end').dispatchEvent(new InputEvent('input',{bubbles:true,inputType:'insertText'}))")
  # Typed starts auto-fill one hour, follow changes, preserve explicit ends.
  ev("openCell('2026-10-24','family')")
  assert ev("!document.getElementById('time').value&&!document.getElementById('end').value")
  start('09:30')
  assert ev("canonicalInput('end')==='10:30'")
  start('10:45')
  assert ev("canonicalInput('end')==='11:45'")
  end('14:00');start('11:00')
  assert ev("canonicalInput('end')==='14:00'")
  # Clearing an explicit end restores the one-hour default when saved.
  end('')
  ev("document.getElementById('title').value='Default duration';document.getElementById('event-form').requestSubmit()")
  assert ev("events.some(e=>e.title==='Default duration'&&e.time==='11:00'&&e.end==='12:00'&&e.endDate==='2026-10-24')")
  # The graphical picker uses the same default, including crossing midnight.
  ev("openCell('2026-10-24','family');document.getElementById('pick-time').click();chooseTime('23:30')")
  assert ev("canonicalInput('end')==='00:30'&&document.getElementById('end-date').value==='2026-10-25'")
  start('22:15')
  assert ev("canonicalInput('end')==='23:15'&&document.getElementById('end-date').value==='2026-10-24'")
  start('23:30')
  ev("document.getElementById('title').value='Overnight hour';document.getElementById('event-form').requestSubmit()")
  assert ev("events.some(e=>e.title==='Overnight hour'&&e.time==='23:30'&&e.end==='00:30'&&e.endDate==='2026-10-25')")
  # Removing an automatically timed start restores an all-day event.
  ev("openCell('2026-10-24','family')");start('23:30');start('')
  assert ev("!document.getElementById('end').value&&document.getElementById('end-date').value==='2026-10-24'")
  ev("document.getElementById('title').value='All day';document.getElementById('event-form').requestSubmit()")
  assert ev("events.some(e=>e.title==='All day'&&!e.time&&!e.end)")
  # Existing explicit durations and selected multi-day end dates are respected.
  ev("openEvent(events.find(e=>e.id==='occupied'),'2026-10-24','family')")
  start('08:30')
  assert ev("canonicalInput('end')==='10:00'")
  ev("document.getElementById('close').click();openCell('2026-10-24','family');document.getElementById('end-date').value='2026-10-28';document.getElementById('end-date').dispatchEvent(new Event('input',{bubbles:true}))")
  start('10:00')
  assert ev("canonicalInput('end')==='11:00'&&document.getElementById('end-date').value==='2026-10-28'")
  # 12-hour entry and AM/PM changes update both the end and the correct date.
  ev("document.getElementById('close').click();preferences.timeFormat='12h';applyTimePreferences();openCell('2026-10-24','family')")
  start('11:30')
  assert ev("document.getElementById('end').value==='12:30'&&document.getElementById('end-period').value==='PM'")
  ev("document.getElementById('time-period').value='PM';document.getElementById('time-period').dispatchEvent(new Event('change',{bubbles:true}))")
  assert ev("canonicalInput('end')==='00:30'&&document.getElementById('end-date').value==='2026-10-25'")
  # Provider submission receives the same calculated one-hour end; no real network.
  ev("""saveOnlineEvent=async item=>{window.capturedEvent=item;document.getElementById('editor').close()};document.getElementById('event-source').add(new Option('Test source','source:test'));document.getElementById('event-source').value='source:test';document.getElementById('title').value='Online hour';document.getElementById('event-form').requestSubmit()""")
  assert ev("capturedEvent.time==='23:30'&&capturedEvent.end==='00:30'&&capturedEvent.endDate==='2026-10-25'")
  assert not errors,errors
  print('PASS: reachable plus on occupied/crowded cells; icon/field/AM-PM geometry across 8 themes, both modes, 24/12h and 3 screen sizes; default hour for typed/picked times, changes, explicit ends, midnight, all-day, multiday and provider save payload.')
  call('Browser.close');proc.wait(timeout=15)
 finally:
  if proc.poll() is None:proc.terminate();proc.wait(timeout=15)

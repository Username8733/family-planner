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

  call('Page.navigate',{'url':(root/'dist/index.html').as_uri()});time.sleep(.1)
  assert ev("key(easterSunday(2024))==='2024-03-31'&&key(easterSunday(2025))==='2025-04-20'&&key(easterSunday(2026))==='2026-04-05'&&key(easterSunday(2008))==='2008-03-23'&&key(easterSunday(2038))==='2038-04-25'")
  for day,name,holiday,flag in [
   ('2026-12-24','Julafton',False,False),('2026-12-25','Juldagen',True,True),('2026-12-26','Annandag jul',True,False),
   ('2026-04-03','Långfredagen',True,False),('2026-04-04','Påskafton',False,False),('2026-04-05','Påskdagen',True,True),('2026-04-06','Annandag påsk',True,False),
   ('2026-05-14','Kristi himmelsfärdsdag',True,False),('2026-05-24','Pingstdagen',True,True),
   ('2026-06-19','Midsommarafton',False,False),('2026-06-20','Midsommardagen',True,True),('2026-10-31','Alla helgons dag',True,False),
   ('2026-10-24','FN-dagen',False,True),('2026-12-23','Drottningens födelsedag',False,True),
   ('2026-09-13','Riksdagsval',False,True),('2010-09-19','Riksdagsval',False,True),('2024-06-09','EU-val',False,True),
   ('2026-11-29','Första advent',False,False),('2026-12-20','Fjärde advent',False,False)
  ]:
   expected=json.dumps({'day':day,'name':name,'holiday':holiday,'flag':flag})
   assert ev("(()=>{const e="+expected+";const d=swedishCalendar(Number(e.day.slice(0,4))).get(e.day);return !!d&&d.names.includes(e.name)&&d.holiday===e.holiday&&d.flag===e.flag})()"),day
  assert ev("swedishCalendar(2026).get('2026-04-30').names.includes('Valborgsmässoafton')&&swedishCalendar(2026).get('2026-04-30').names.includes('Kungens födelsedag')")
  assert ev("swedishCalendar(2008).get('2008-05-01').names.includes('Första maj')&&swedishCalendar(2008).get('2008-05-01').names.includes('Kristi himmelsfärdsdag')")
  assert ev("!swedishCalendar(2004).get('2004-06-06').holiday&&swedishCalendar(2005).get('2005-06-06').holiday&&!swedishCalendar(2017).get('2017-05-29')&&swedishCalendar(2018).get('2018-05-29').flag")
  # Generated dates remain valid and movable feasts remain on the required weekdays.
  assert ev("""(()=>{for(let year=2000;year<=2100;year++){for(const date of swedishCalendar(year).keys())if(!validDate(date)||!date.startsWith(year+'-'))return false;const e=easterSunday(year);if(e.getDay()!==0||e.getMonth()<2||e.getMonth()>3)return false;const days=[...swedishCalendar(year)].filter(([date,v])=>v.names.includes('Midsommardagen'));if(days.length!==1||makeDate(days[0][0]).getDay()!==6||Number(days[0][0].slice(8))<20||Number(days[0][0].slice(8))>26)return false}return true})()""")
  before=ev("JSON.stringify(events)")
  for theme in ['home','sage','ocean','sand','plum','start']:
   for mode in ['light','dark']:
    for label,w,h in [('desktop',1440,1000),('ipad-landscape',1024,768),('ipad-portrait',768,1024)]:
     call('Emulation.setDeviceMetricsOverride',{'width':w,'height':h,'deviceScaleFactor':1,'mobile':False})
     ev("month=new Date(2026,11,1);appearance={theme:"+json.dumps(theme)+",mode:"+json.dumps(mode)+"};applyAppearance();render()")
     time.sleep(.04)
     assert ev("document.getElementById('calendar').scrollHeight<=document.getElementById('calendar').clientHeight+1"),str((theme,mode,label))
     assert ev("""(()=>{const c=document.querySelector('.cell[data-date="2026-12-24"]'),th=c.closest('tr').querySelector('th'),name=th.querySelector('.holiday-name');return name.textContent==='Julafton'&&name.scrollWidth<=name.clientWidth+1&&!th.querySelector('.holiday-flag')&&!c.closest('tr').classList.contains('public-holiday')})()"""),str((theme,mode,label,'Christmas Eve'))
     assert ev("""(()=>{const tr=document.querySelector('.cell[data-date="2026-12-25"]').closest('tr');return tr.classList.contains('public-holiday')&&tr.querySelector('.holiday-flag').getAttribute('aria-label').includes('Juldagen')})()""")
     if theme=='start' and label in ['desktop','ipad-portrait']:
      shot=call('Page.captureScreenshot',{'format':'png','captureBeyondViewport':False});(qa/('holidays-'+mode+'-'+label+'.png')).write_bytes(base64.b64decode(shot['data']))
  assert ev("JSON.stringify(events)")==before,'Observances must not mutate family events'
  ev("month=new Date(2026,9,1);render()")
  assert ev("""document.querySelector('.cell[data-date="2026-10-24"]').closest('tr').querySelector('.holiday-flag')!==null""")
  assert not errors,errors
  print('PASS: fixed/movable holidays, Christmas Eve, Advent, elections, merged occasions, historical rule changes, 2000–2100 dates, flags and accessibility, no event data mutation; month fits all 12 theme variants on desktop and both iPad orientations.')
  call('Browser.close');proc.wait(timeout=15)
 finally:
  if proc.poll() is None:proc.terminate();proc.wait(timeout=15)

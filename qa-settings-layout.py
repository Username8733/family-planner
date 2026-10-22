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


  call('Page.navigate',{'url':(root/'dist/index.html').as_uri()});time.sleep(.35)
  for label,w,h in [('desktop',1440,1000),('ipad',768,1024),('landscape',1024,768)]:
   call('Emulation.setDeviceMetricsOverride',{'width':w,'height':h,'deviceScaleFactor':1,'mobile':False})
   for theme in ['start','ios','eink']:
    for mode in ['light','dark']:
     ev("appearance={theme:"+json.dumps(theme)+",mode:"+json.dumps(mode)+"};applyAppearance();document.getElementById('columns').click()")
     ev("document.querySelector('#column-editor>.dialog-content').scrollTop=99999")
     d=ev("""(()=>{const dialog=document.getElementById('column-editor'),body=dialog.querySelector(':scope>.dialog-content'),footer=dialog.querySelector('.settings-footer'),save=document.getElementById('save-columns');const a=dialog.getBoundingClientRect(),b=body.getBoundingClientRect(),f=footer.getBoundingClientRect(),s=save.getBoundingClientRect();return {outerOverflow:getComputedStyle(dialog).overflowY,scrolling:body.scrollHeight>body.clientHeight,top:b.top-a.top,bottom:a.bottom-f.bottom,overlap:b.bottom-f.top,button:s.bottom<=f.bottom&&s.top>=f.top,footerPosition:getComputedStyle(footer.querySelector('.column-actions')).position}})()""")
     assert d['outerOverflow']=='hidden' and d['scrolling'] and d['top']>25 and d['bottom']>=0 and d['overlap']<1 and d['button'] and d['footerPosition']=='static',(label,theme,mode,d)
     if theme=='ios' and label in ['desktop','ipad']:
      shot=call('Page.captureScreenshot',{'format':'png','captureBeyondViewport':False});(qa/('settings-fixed-'+label+'-'+mode+'.png')).write_bytes(base64.b64decode(shot['data']))
     ev("document.getElementById('cancel-columns').click()")
  # A city is selected once; the result list disappears and searching remains possible.
  ev("""document.getElementById('columns').click();fetchJson=async()=>({results:[{name:'Stockholm',country:'Sweden',latitude:59.3,longitude:18.1},{name:'Uppsala',country:'Sweden',latitude:59.8,longitude:17.6}]});document.getElementById('weather-city').value='Stockholm';document.getElementById('search-city').click()""")
  time.sleep(.1);assert ev("document.querySelectorAll('.city-result').length===2")
  ev("document.querySelector('.city-result').click()")
  assert ev("document.querySelectorAll('.city-result').length===0&&locationDraft.name.includes('Stockholm')&&document.getElementById('weather-city').value===locationQuery")
  ev("document.getElementById('weather-city').value='Uppsala';document.getElementById('search-city').click()")
  time.sleep(.1);assert ev("document.querySelectorAll('.city-result').length===2")
  assert not errors,errors
  print('PASS: internal scrolling clipped away from rounded corners, fixed footer without overlap, all buttons visible, six theme variants on desktop and iPad; city results dismiss after selection and can be searched again.')
  call('Browser.close');proc.wait(timeout=15)
 finally:
  if proc.poll() is None:proc.terminate();proc.wait(timeout=15)

"""Actual HTTP/WebSocket HA protocol fixture, no real Home Assistant used."""
import asyncio,json,tempfile,threading,copy
from pathlib import Path
from aiohttp import web
from calendar_sources import CalendarSources
from online_calendar import ICloudCalendar,CalendarError
event={'uid':'ha-uid','recurrence_id':'2026-10-24','summary':'Person 5 - HA test','start':'2026-10-24','end':'2026-10-25','description':'Keep description','location':'Home'}
expected_details={'description':'Keep description','location':'Home'}
commands=[];ready=threading.Event();loop=asyncio.new_event_loop();holder={}
async def route(request):
    assert request.headers.get('Authorization')=='Bearer fixture-ha-token-private'
    if request.path=='/api/calendars':return web.json_response([{'entity_id':'calendar.test','name':'HA Test'}])
    if request.path=='/api/states':return web.json_response([{'entity_id':'calendar.test','attributes':{'supported_features':7}}])
    return web.json_response([event] if event else [])
async def websocket(request):
    ws=web.WebSocketResponse();await ws.prepare(request)
    await ws.send_json({'type':'auth_required'})
    auth=await ws.receive_json();assert auth['access_token']=='fixture-ha-token-private'
    await ws.send_json({'type':'auth_ok'})
    command=await ws.receive_json();commands.append(command)
    assert command['entity_id']=='calendar.test' and command['uid']=='ha-uid'
    assert command['recurrence_id']=='2026-10-24' and 'recurrence_range' not in command
    if command['type']=='calendar/event/update':
        assert all(command['event'][k]==v for k,v in expected_details.items())
        event.update(summary=command['event']['summary'],start=command['event']['dtstart'],end=command['event']['dtend'],description=command['event']['description'],location=command['event']['location'])
    else:
        assert command['type']=='calendar/event/delete';event.clear()
    await ws.send_json({'id':command['id'],'type':'result','success':True})
    await ws.close();return ws
async def start():
    app=web.Application();app.router.add_get('/api/websocket',websocket);app.router.add_get('/api/{tail:.*}',route)
    runner=web.AppRunner(app);await runner.setup();site=web.TCPSite(runner,'127.0.0.1',0);await site.start()
    holder['runner']=runner;holder['url']='http://127.0.0.1:'+str(site._server.sockets[0].getsockname()[1]);ready.set()
def run():
    asyncio.set_event_loop(loop);loop.run_until_complete(start());loop.run_forever()
thread=threading.Thread(target=run,daemon=True);thread.start();assert ready.wait(5)
try:
    with tempfile.TemporaryDirectory(prefix='hemma-ha-ws-') as folder:
        sources=CalendarSources(ICloudCalendar(Path(folder)/'icloud.json'))
        sources.add({'type':'ha','url':holder['url'],'token':'fixture-ha-token-private'})
        e=sources.events('2026-10-01','2026-11-01')['events'][0]
        assert e['writable'] and e['canDelete'] and e['canUpdate'] and e['recurring']
        item=dict(e,summary='Person 5 - HA edited',endDate=e['editEndDate']);item.pop('description');item.pop('location')
        sources.mutate('PUT',item);assert event['summary']==item['summary'] and len(commands)==1
        try:sources.mutate('DELETE',e);raise AssertionError('Stale HA event accepted')
        except CalendarError as err:assert err.status==409
        fresh=sources.events('2026-10-01','2026-11-01')['events'][0]
        assert fresh['description']=='Keep description' and fresh['location']=='Home'
        expected_details.update(description='Updated notes',location='Room B')
        sources.mutate('PUT',dict(fresh,description='Updated notes',location='Room B',endDate=fresh['editEndDate']))
        fresh=sources.events('2026-10-01','2026-11-01')['events'][0]
        assert fresh['description']=='Updated notes' and fresh['location']=='Room B'
        expected_details.update(description='',location='')
        sources.mutate('PUT',dict(fresh,description='',location='',endDate=fresh['editEndDate']))
        fresh=sources.events('2026-10-01','2026-11-01')['events'][0]
        assert fresh['description']=='' and fresh['location']==''
        sources.mutate('DELETE',fresh);assert not event and len(commands)==4
        assert not sources.events('2026-10-01','2026-11-01')['events']
        print('PASS: HA websocket authentication, capabilities, recurring occurrence update/delete, description/location preservation and stale edit rejection.')
finally:
    asyncio.run_coroutine_threadsafe(holder['runner'].cleanup(),loop).result(5);loop.call_soon_threadsafe(loop.stop);thread.join(5)

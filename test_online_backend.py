
import json,os,socket,subprocess,sys,tempfile,time,urllib.request
from pathlib import Path
from online_calendar import ICloudCalendar,CalendarError
from datetime import datetime
from zoneinfo import ZoneInfo

root=Path(__file__).parent
with tempfile.TemporaryDirectory(prefix='hemma-caldav-test-') as temp:
    temp=Path(temp)
    sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1];sock.close()
    log=(temp/'server.log').open('w+')
    proc=subprocess.Popen([sys.executable,'-m','xandikos.web','--no-detect-systemd','--defaults','-d',str(temp/'dav'),'--state-dir',str(temp/'state'),'-l','127.0.0.1','-p',str(port)],stdout=log,stderr=log)
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(f'http://127.0.0.1:{port}/',timeout=.2)
                break
            except Exception:time.sleep(.05)
        backend=ICloudCalendar(temp/'private/icloud.json',server_url=f'http://127.0.0.1:{port}/')
        result=backend.connect('test@example.invalid','local-test-password')
        assert result['calendars'],result
        backend.select(result['calendars'][0]['id'])
        assert os.stat(backend.config_file).st_mode&0o777==0o600
        item={'summary':'Person 5, Person 4 - Cinema','date':'2026-10-24','endDate':'2026-10-24','time':'15:00','end':'17:00'}
        backend.create(item)
        results=backend.events('2026-10-01','2026-11-01')['events']
        assert len(results)==1,results
        # iCloud's discovered calendar lives on another hostname than discovery.
        # Use two loopback hostnames for the same real CalDAV server.
        original_url=backend.config['calendar_url']
        backend.config['calendar_url']=original_url.replace('127.0.0.1','localhost')
        try:
            shard_results=backend.events('2026-10-01','2026-11-01')['events']
            assert len(shard_results)==1 and shard_results[0]['summary']==item['summary']
        finally:
            backend.config['calendar_url']=original_url
        event=results[0]
        assert event['summary']==item['summary'] and event['time']=='15:00' and event['etag'],event
        backend.update(event['id'],event['etag'],dict(item,summary='Person 5 - Dance'))
        updated=backend.events('2026-10-01','2026-11-01')['events'][0]
        assert updated['summary']=='Person 5 - Dance'
        try:
            backend.update(event['id'],event['etag'],item)
            raise AssertionError('Stale ETag accepted')
        except CalendarError as error:assert error.status==409
        backend.delete(updated['id'],updated['etag'])
        assert not backend.events('2026-10-01','2026-11-01')['events']
        backend.create(dict(item,summary='Person 5 - Autumn break',date='2026-10-30',endDate='2026-11-02',time='',end=''))
        all_day=backend.events('2026-11-01','2026-12-01')['events'][0]
        assert all_day['date']=='2026-10-30' and all_day['endDate']=='2026-11-02' and all_day['allDay']
        # Real CalDAV recurrence expansion and per-occurrence update/delete.
        import caldav
        with backend._client() as client:
            calendar=caldav.Calendar(client=client,url=backend._selected())
            calendar.add_event(dtstart=datetime(2026,10,20,18,tzinfo=ZoneInfo('Europe/Stockholm')),
                               dtend=datetime(2026,10,20,19,tzinfo=ZoneInfo('Europe/Stockholm')),
                               uid='recurrence-test',summary='Person 5 - Weekly practice',rrule={'FREQ':'WEEKLY','COUNT':4},
                               description='Keep the description',location='Sports hall')
        occurrences=[e for e in backend.events('2026-10-01','2026-11-20')['events'] if e['summary']=='Person 5 - Weekly practice']
        assert len(occurrences)==4,occurrences
        chosen=next(e for e in occurrences if e['date']=='2026-10-27')
        backend.update(chosen['id'],chosen['etag'],dict(item,date='2026-10-28',endDate='2026-10-28',summary='Person 5 - Rescheduled practice'))
        reread=backend.events('2026-10-01','2026-11-20')['events']
        assert sum(e['summary']=='Person 5 - Weekly practice' for e in reread)==3,reread
        changed=next(e for e in reread if e['summary']=='Person 5 - Rescheduled practice')
        assert changed['date']=='2026-10-28'
        backend.delete(changed['id'],changed['etag'])
        remaining=backend.events('2026-10-01','2026-11-20')['events']
        assert sum(e['summary']=='Person 5 - Weekly practice' for e in remaining)==3
        assert not any(e['summary']=='Person 5 - Rescheduled practice' for e in remaining)
        # Nonexistent DST wall-clock times must not silently shift.
        try:
            backend.create(dict(item,date='2026-03-29',endDate='2026-03-29',time='02:30',end='04:00'))
            raise AssertionError('Nonexistent DST time accepted')
        except CalendarError as error:assert 'daylight-saving' in str(error)
        # A title-only edit must retain the second occurrence of an ambiguous hour.
        with backend._client() as client:
            calendar=caldav.Calendar(client=client,url=backend._selected())
            calendar.add_event(uid='autumn-fold',summary='Person 5 - Late hour',
                dtstart=datetime(2026,10,25,2,30,tzinfo=ZoneInfo('Europe/Stockholm'),fold=1).astimezone(ZoneInfo('UTC')),
                dtend=datetime(2026,10,25,3,30,tzinfo=ZoneInfo('Europe/Stockholm')).astimezone(ZoneInfo('UTC')))
        fold=next(e for e in backend.events('2026-10-01','2026-11-01')['events'] if e['summary']=='Person 5 - Late hour')
        backend.update(fold['id'],fold['etag'],dict(item,summary='Person 5 - Updated late hour',date=fold['date'],endDate=fold['editEndDate'],time=fold['time'],end=fold['editEndTime']))
        with backend._client() as client:
            ref=backend._decode(fold['id']);ical,_=backend._fetch(client,ref['url'])
            start=ical.walk('VEVENT')[0].decoded('DTSTART').astimezone(ZoneInfo('UTC'))
            assert start.hour==1 and start.minute==30,start
        import uuid
        request_id=str(uuid.uuid4())
        retried=dict(item,summary='Person 5 - Save once',requestId=request_id)
        backend.create(retried)
        assert backend.create(retried)['alreadySaved']
        assert sum(e['summary']=='Person 5 - Save once' for e in backend.events('2026-10-01','2026-11-01')['events'])==1
        try:
            backend.create(dict(retried,summary='Person 5 - Do not overwrite'))
            raise AssertionError('Idempotent create overwrote data')
        except CalendarError as error:assert error.status==409
        print('PASS: real CalDAV discovery, private credential storage, timed/all-day events, CRUD, conflict protection, recurring exceptions and deletion, cross-month spans, DST rejection.')
    except Exception:
        log.flush();print((temp/'server.log').read_text()[-3000:])
        raise
    finally:
        proc.terminate();proc.wait(timeout=10);log.close()

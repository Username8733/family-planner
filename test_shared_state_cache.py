"""Shared settings and event cache persistence, conflicts and refresh behavior."""
import copy
import json
import os
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from event_cache import EventCache
from planner_state import PlannerState
from online_calendar import CalendarError,ICloudCalendar
from serve import CalendarHTTPServer,Handler

def state():
    return {"version":3,"people":[{"id":"family","name":"Shared","initial":"SH","color":"#5e7359"}],
            "events":[],"appearance":{"theme":"ios","mode":"dark"},"preferences":{"language":"sv","calendarMode":"icloud"},"touch":True}

class SharedTests(unittest.TestCase):
    def test_state_survives_restart_and_rejects_stale_writes_and_secrets(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"planner-state.json"; store=PlannerState(path)
            self.assertEqual(store.get(),{"revision":0,"state":None})
            store.put({"revision":0,"state":state()})
            self.assertEqual(PlannerState(path).get()["state"]["appearance"]["theme"],"ios")
            self.assertEqual(path.stat().st_mode&0o777,0o600)
            with self.assertRaises(CalendarError) as err:store.put({"revision":0,"state":state()})
            self.assertEqual(err.exception.status,409)
            bad=state(); bad["preferences"]["password"]="must-not-be-stored"
            with self.assertRaises(CalendarError):store.put({"revision":1,"state":bad})
            self.assertNotIn("must-not-be-stored",path.read_text())
    def test_http_shared_state_needs_csrf_and_is_not_static(self):
        with tempfile.TemporaryDirectory() as folder:
            server=CalendarHTTPServer(("127.0.0.1",0),Path(__file__).parent/"dist",ICloudCalendar(Path(folder)/"icloud.json"))
            threading.Thread(target=server.serve_forever,daemon=True).start()
            base="http://127.0.0.1:"+str(server.server_port)
            def request(path,data=None,token=None):
                headers={"Content-Type":"application/json"}
                if token:headers["X-Hemma-CSRF"]=token
                req=urllib.request.Request(base+path,None if data is None else json.dumps(data).encode(),headers=headers,method="GET" if data is None else "PUT")
                try:r=urllib.request.urlopen(req)
                except urllib.error.HTTPError as e:r=e
                with r:
                    raw=r.read()
                    try:body=json.loads(raw)
                    except ValueError:body=None
                    return r.status,body
            try:
                session=request("/api/session")[1]
                self.assertEqual(request("/api/state",{"revision":0,"state":state()})[0],403)
                self.assertEqual(request("/api/state",{"revision":0,"state":state()},session["csrf"])[0],200)
                other_device=request("/api/state")[1]
                self.assertEqual(other_device["state"]["preferences"]["language"],"sv")
                self.assertEqual(request("/planner-state.json")[0],404)
            finally:server.shutdown();server.server_close()

class CacheTests(unittest.TestCase):
    def test_hit_restart_background_refresh_and_invalidation(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"events.sqlite3"; now=[1000]; calls=[]
            def fetch():
                calls.append(1)
                return {"events":[{"id":"first","sourceKey":"cal:one","writable":True}],"errors":[]}
            cache=EventCache(path,clock=lambda:now[0])
            try:
                self.assertFalse(cache.get("month",fetch)["cache"]["hit"])
                self.assertTrue(cache.get("month",fetch)["cache"]["hit"])
                self.assertEqual(len(calls),1)
            finally:cache.close()
            cache=EventCache(path,clock=lambda:now[0])
            try:
                self.assertTrue(cache.get("month",fetch)["cache"]["hit"])
                self.assertEqual(len(calls),1)
                now[0]+=181; ready=threading.Event(); release=threading.Event()
                def slow():
                    ready.set(); release.wait(3)
                    return {"events":[{"id":"new","sourceKey":"cal:one","writable":True}],"errors":[]}
                started=time.monotonic(); result=cache.get("month",slow)
                self.assertLess(time.monotonic()-started,.2)
                self.assertTrue(result["cache"]["refreshing"]);self.assertFalse(result["events"][0]["writable"])
                self.assertTrue(ready.wait(1)); task=cache.pending["month"][1]
                cache.invalidate(); release.set(); task.result(3)
                result=cache.get("month",lambda:{"events":[{"id":"after-edit"}],"errors":[]})
                self.assertEqual(result["events"][0]["id"],"after-edit")
                self.assertFalse(result["cache"]["hit"])
                self.assertEqual(path.stat().st_mode&0o777,0o600)
            finally:cache.close()
    def test_partial_failure_retains_read_only_last_events(self):
        with tempfile.TemporaryDirectory() as folder:
            cache=EventCache(Path(folder)/"events.sqlite3")
            try:
                cache.get("m",lambda:{"events":[{"id":"kept","sourceKey":"one","writable":True}],"errors":[]})
                release=threading.Event()
                def fail():
                    release.wait(2)
                    return {"events":[],"errors":[{"sourceKey":"one","name":"Calendar","error":"Unavailable"}]}
                cache.get("m",fail,force=True); task=cache.pending["m"][1]; release.set(); task.result(3)
                result=cache.get("m",fail)
                self.assertEqual(result["events"][0]["id"],"kept")
                self.assertTrue(result["events"][0]["stale"]);self.assertFalse(result["events"][0]["writable"])
                self.assertTrue(result["errors"])
            finally:cache.close()

if __name__=="__main__":
    Handler.log_message=lambda *args:None
    unittest.main()

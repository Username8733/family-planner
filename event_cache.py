"""Private persistent event cache with background refresh and generation guards."""
import copy
import json
import os
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

class EventCache:
    def __init__(self,path,ttl=180,clock=time.time):
        self.path=Path(path); self.path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.db=sqlite3.connect(self.path,check_same_thread=False)
        os.chmod(self.path,0o600)
        self.db.execute("CREATE TABLE IF NOT EXISTS events (cache_key TEXT PRIMARY KEY,payload TEXT NOT NULL,fetched REAL NOT NULL)")
        self.db.commit()
        self.ttl=ttl; self.clock=clock; self.lock=threading.RLock()
        self.pool=ThreadPoolExecutor(max_workers=3,thread_name_prefix="calendar-cache")
        self.pending={}; self.generation=0; self.closed=False
    def invalidate(self):
        with self.lock:
            self.generation+=1
            self.db.execute("DELETE FROM events"); self.db.commit()
    def _entry(self,key):
        row=self.db.execute("SELECT payload,fetched FROM events WHERE cache_key=?",(key,)).fetchone()
        return (json.loads(row[0]),row[1]) if row else None
    def _refresh(self,key,fetch,generation,old):
        try:
            try:
                result=fetch()
            except Exception:
                keys={e.get("sourceKey","cache") for e in old[0].get("events",[])} if old else {"cache"}
                result={"events":[],"errors":[{"sourceKey":k,"name":"Online calendars","error":"Could not fetch the calendar. Try refreshing again."} for k in keys]}
            failed={e["sourceKey"] for e in result.get("errors",[])}
            if failed and old:
                retained=[dict(e,writable=False,canUpdate=False,canDelete=False,stale=True) for e in old[0]["events"] if e.get("sourceKey") in failed]
                result={**result,"events":result["events"]+retained}
            with self.lock:
                if not self.closed and generation==self.generation:
                    self.db.execute("INSERT OR REPLACE INTO events VALUES (?,?,?)",(key,json.dumps(result,ensure_ascii=False,allow_nan=False),self.clock()))
                    self.db.execute("DELETE FROM events WHERE cache_key NOT IN (SELECT cache_key FROM events ORDER BY fetched DESC LIMIT 24)")
                    self.db.commit()
            return result
        finally:
            with self.lock:
                item=self.pending.get(key)
                if item and item[0]==generation:
                    self.pending.pop(key,None)
    def get(self,key,fetch,force=False):
        with self.lock:
            entry=self._entry(key)
            age=self.clock()-entry[1] if entry else None
            ttl=10 if entry and entry[0].get("errors") else self.ttl
            fresh=entry and 0<=age<ttl and not force
            generation=self.generation
            task=self.pending.get(key)
            if task and task[0]!=generation:
                task=None
            if not fresh and not task:
                # The future cannot enter _refresh's final lock until registered.
                future=self.pool.submit(self._refresh,key,fetch,generation,entry)
                task=(generation,future); self.pending[key]=task
            if entry:
                result=copy.deepcopy(entry[0])
                if not fresh:
                    result["events"]=[dict(e,writable=False,canUpdate=False,canDelete=False,stale=True) for e in result["events"]]
                return {**result,"cache":{"hit":True,"refreshing":bool(task),"stale":not bool(fresh),"fetchedAt":entry[1]}}
        result=task[1].result()
        with self.lock:
            if generation!=self.generation:
                return self.get(key,fetch,False)
        return {**copy.deepcopy(result),"cache":{"hit":False,"refreshing":False,"stale":False,"fetchedAt":self.clock()}}
    def close(self):
        with self.lock:
            self.closed=True
        self.pool.shutdown(wait=True,cancel_futures=True)
        self.db.close()

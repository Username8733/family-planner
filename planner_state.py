"""Private, revisioned shared planner state. Provider credentials live elsewhere."""
import copy
import json
import os
import re
import tempfile
import threading
from datetime import date
from pathlib import Path
from online_calendar import CalendarError

THEMES = {"home", "sage", "ocean", "sand", "plum", "start", "eink", "ios"}

def validate_state(value):
    def fail():
        raise CalendarError("Invalid planner settings.", 400)
    if not isinstance(value, dict) or set(value) - {"version","people","events","preferences","appearance","touch"}:
        fail()
    columns = value.get("people")
    if not isinstance(columns, list) or not 1 <= len(columns) <= 32:
        fail()
    clean_columns = []
    ids, names = set(), set()
    for p in columns:
        if not isinstance(p, dict) or set(p) - {"id","name","color","initial","aliases"}:
            fail()
        ident, name, color = p.get("id"), p.get("name"), p.get("color")
        if not isinstance(ident,str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}",ident) or ident in ids:
            fail()
        if not isinstance(name,str) or not name.strip() or len(name)>30 or name.casefold() in names:
            fail()
        if not isinstance(color,str) or not re.fullmatch(r"#[a-fA-F0-9]{6}",color):
            fail()
        aliases=p.get("aliases",[])
        if not isinstance(aliases,list) or len(aliases)>100 or any(not isinstance(a,str) or len(a)>100 for a in aliases):
            fail()
        ids.add(ident); names.add(name.casefold())
        clean_columns.append({"id":ident,"name":name.strip(),"color":color,"initial":str(p.get("initial",name[:2]))[:10],"aliases":aliases})
    entries=value.get("events",[])
    if not isinstance(entries,list) or len(entries)>10000:
        fail()
    clean_events=[]; event_ids=set()
    for e in entries:
        if not isinstance(e,dict) or set(e)-{"id","title","date","endDate","people","time","end","person"}:
            fail()
        try:
            first=date.fromisoformat(e["date"]); last=date.fromisoformat(e.get("endDate",e["date"]))
            if first.year<2000 or last.year>2100 or last<first:
                fail()
        except (ValueError,TypeError,KeyError):
            fail()
        if not isinstance(e.get("id"),str) or not 1<=len(e["id"])<=200 or e["id"] in event_ids:
            fail()
        if not isinstance(e.get("title"),str) or not e["title"].strip() or len(e["title"])>80:
            fail()
        participants=e.get("people",[e.get("person")])
        if not isinstance(participants,list) or not participants or any(p not in ids for p in participants):
            fail()
        for key in ("time","end"):
            if not isinstance(e.get(key,""),str) or e.get(key) and not re.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]",e[key]):
                fail()
        if first==last and e.get("time") and e.get("end") and e["end"]<=e["time"]:
            fail()
        event_ids.add(e["id"])
        clean_events.append({k:e[k] for k in ("id","title","date")}|{"endDate":last.isoformat(),"people":list(dict.fromkeys(participants)),"time":e.get("time",""),"end":e.get("end","")})
    pref=value.get("preferences",{})
    allowed={"language","timeFormat","temperatureUnit","weatherLocation","temperatureSource","temperatureEntity","calendarMode","onlineFallback"}
    if not isinstance(pref,dict) or set(pref)-allowed:
        fail()
    defaults={"language":"en","timeFormat":"24h","temperatureUnit":"celsius","weatherLocation":None,"temperatureSource":"weather","temperatureEntity":"","calendarMode":"local","onlineFallback":columns[0]["id"]}
    pref=defaults|pref
    for k,choices in {"language":{"sv","en"},"timeFormat":{"24h","12h"},"temperatureUnit":{"celsius","fahrenheit"},"temperatureSource":{"weather","ha"},"calendarMode":{"local","icloud","mixed"}}.items():
        if not isinstance(pref[k],str) or pref[k] not in choices:
            fail()
    if pref["onlineFallback"] not in ids:
        pref["onlineFallback"]=clean_columns[0]["id"]
    sensor=pref["temperatureEntity"]
    if not isinstance(sensor,str) or sensor and not re.fullmatch(r"sensor\.[a-z0-9_]+",sensor):
        fail()
    loc=pref["weatherLocation"]
    if loc is not None:
        if not isinstance(loc,dict) or set(loc)-{"name","latitude","longitude"} or not isinstance(loc.get("name"),str) or len(loc["name"])>200:
            fail()
        for k,bound in (("latitude",90),("longitude",180)):
            n=loc.get(k)
            if isinstance(n,bool) or not isinstance(n,(float,int)) or not -bound<=n<=bound:
                fail()
    look=value.get("appearance",{})
    if not isinstance(look,dict) or set(look)-{"theme","mode"} or look.get("theme") not in THEMES or look.get("mode") not in {"light","dark"}:
        fail()
    if not isinstance(value.get("touch",False),bool):
        fail()
    return {"version":3,"people":clean_columns,"events":clean_events,"preferences":pref,"appearance":look,"touch":value.get("touch",False)}

class PlannerState:
    def __init__(self,path):
        self.path=Path(path); self.lock=threading.RLock()
        self.value=json.loads(self.path.read_text()) if self.path.exists() else {"revision":0,"state":None}
    def get(self):
        with self.lock:
            return copy.deepcopy(self.value)
    def put(self,body):
        if not isinstance(body,dict) or set(body)-{"revision","state"} or type(body.get("revision")) is not int:
            raise CalendarError("Invalid settings revision.",400)
        state=validate_state(body.get("state"))
        with self.lock:
            if body["revision"]!=self.value["revision"]:
                raise CalendarError("The planner changed on another device. Reload before saving your changes.",409)
            updated={"revision":self.value["revision"]+1,"state":state}
            self.path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
            fd,name=tempfile.mkstemp(prefix=".planner-state-",dir=self.path.parent)
            try:
                os.fchmod(fd,0o600)
                with os.fdopen(fd,"w") as f:
                    json.dump(updated,f,ensure_ascii=False,allow_nan=False); f.flush(); os.fsync(f.fileno())
                os.replace(name,self.path)
            finally:
                if os.path.exists(name): os.unlink(name)
            self.value=updated
            return self.get()

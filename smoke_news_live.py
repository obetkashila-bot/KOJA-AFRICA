import os, sys, json
os.environ.update(SECRET_KEY="test-secret-key-123456", SUPABASE_URL="https://x.supabase.co",
                  SUPABASE_SECRET_KEY="k", SITE_URL="http://localhost", SESSION_COOKIE_SECURE="false")
sys.path.insert(0, ".")
import app as A

# ---------- fakes ----------
DB, CALLS = {}, {"first_row": 0}
def _m(r, f): return all(str(r.get(k)) == str(v) for k, v in (f or {}).items())
def f_select(t, filters=None, select="*", order=None, limit=None):
    rows = [dict(r) for r in DB.get(t, []) if _m(r, filters)]
    return list(reversed(rows))[: (limit or 10**6)] if order and "desc" in order else rows[: (limit or 10**6)]
def f_insert(t, p, returning="representation"): DB.setdefault(t, []).append(json.loads(json.dumps(p))); return [p], None
def f_update(t, f, p):
    for r in DB.get(t, []):
        if _m(r, f): r.update(json.loads(json.dumps(p)))
    return True, None
def f_first(t, f):
    CALLS["first_row"] += 1; rows = f_select(t, f, limit=1); return rows[0] if rows else None
A.db_select, A.db_insert, A.db_update, A.first_row = f_select, f_insert, f_update, f_first

UID = "a" * 32
CF = {"live_inputs": {}}
def f_cf(method, path, payload=None):
    if method == "POST" and path == "/live_inputs":
        CF["created_payload"] = payload; CF["live_inputs"][UID] = True; return {"uid": UID}, None
    if method == "GET" and path.startswith("/live_inputs/"):
        uid = path.rsplit("/", 1)[1]
        if uid not in CF["live_inputs"]: return None, "Cloudflare: not found"
        return {"uid": uid, "enabled": True, "status": "connected",
                "rtmps": {"url": "rtmps://live.cloudflare.com:443/live/", "streamKey": "SECRETKEY123"},
                "srt": {"url": "srt://live.cloudflare.com:778", "streamId": "SID999", "passphrase": "PASSPH456"}}, None
    return None, "unexpected"
A._cf_stream = f_cf
A.CF_ACCOUNT_ID, A.CF_STREAM_API_TOKEN = "acct", "tok"      # so _cf_configured() is true

LIFE = {"live": False}
class R:
    def __init__(s, j): s._j = j; s.ok = True
    def json(s): return s._j
_real_get = A.requests.get
def f_get(url, **kw):
    if "lifecycle" in url: return R({"isInput": True, "live": LIFE["live"]})
    raise A.requests.exceptions.ConnectionError("offline in tests")
A.requests.get = f_get

ADMIN = {"id": "99999999-9999-9999-9999-999999999999", "full_name": "A", "role": "admin", "is_admin": True, "is_active": True}
USER = dict(ADMIN, id="11111111-1111-1111-1111-111111111111", is_admin=False, role="student")
WHO = {"u": ADMIN}
A.current_user = lambda: WHO["u"]
A.app.config["TESTING"] = True; A.app.config["PROPAGATE_EXCEPTIONS"] = False
c = A.app.test_client()
with c.session_transaction() as s: s["_csrf_token"] = "tok"
H = {"X-CSRF-Token": "tok"}
res = []
def ok(name, cond, extra=""):
    print(("PASS" if cond else "FAIL"), "-", name, ("" if cond else f"   {extra}")); res.append(bool(cond)); return cond
P = lambda url, body=None: c.post(url, json=body or {}, headers=H)
pub = lambda: (A._news_cache_clear(), c.get("/api/news/live/state").get_json())[1]

# 1 access control
WHO["u"] = USER
ok("non-admin blocked from studio page", c.get("/admin/news/live").status_code == 302)
ok("non-admin blocked from control API", P("/api/admin/news/live/go-live").status_code == 302)
ok("non-admin blocked from ingest keys", c.get("/api/admin/news/live/ingest").status_code == 302)
WHO["u"] = ADMIN

# 2 pages render
r = c.get("/admin/news/live"); ok("studio page renders", r.status_code == 200 and b"KOJA NEWS Live Studio" in r.data, r.status_code)
r = c.get("/news/live"); ok("public page renders + nav link", r.status_code == 200 and b"nlpStage" in r.data and b"Live News" in r.data, r.status_code)
r = c.get("/news/live/embed"); ok("embed page renders", r.status_code == 200 and b"nlpStage" in r.data and b"<html" in r.data)
ok("sitemap lists /news/live", b"/news/live" in c.get("/sitemap.xml").data)

# 3 initial state
s = pub(); ok("starts offline, no stream url", s["status"] == "offline" and s["hls_url"] == "")
d = c.get("/api/admin/news/live/ingest").get_json(); ok("ingest: configured, no input yet", d["configured"] and d["uid"] == "")

# 4 go-live blocked without source
r = P("/api/admin/news/live/go-live"); ok("go-live refused without playback source", r.status_code == 400)

# 5 provision
r = P("/api/admin/news/live/provision"); ok("provision creates live input", r.status_code == 200 and r.get_json()["state"]["cf_input_uid"] == UID)
ok("provision asked for auto-recording", CF["created_payload"]["recording"]["mode"] == "automatic" and "preferLowLatency" not in CF["created_payload"])
ok("second provision -> 409", P("/api/admin/news/live/provision").status_code == 409)
d = c.get("/api/admin/news/live/ingest").get_json()
ok("ingest returns RTMPS+SRT creds to admin", d["rtmps"]["key"] == "SECRETKEY123" and d["srt"]["passphrase"] == "PASSPH456" and d["encoder_live"] is None)  # unknown until customer code is set
ok("keys NOT stored in DB", "SECRETKEY123" not in json.dumps(DB) and "PASSPH456" not in json.dumps(DB))

# 6 customer code needed for playback
r = P("/api/admin/news/live/go-live"); ok("go-live refused until customer code set", r.status_code == 400)
A._CF_CUSTOMER_RAW = "customer-abc123.cloudflarestream.com"
ok("customer code normalised", A._cf_customer_code() == "abc123")
r = P("/api/admin/news/live/go-live"); ok("go-live succeeds", r.status_code == 200 and r.get_json()["state"]["on_air"] is True)

# 7 public status follows encoder health
LIFE["live"] = False; s = pub(); ok("on air but encoder silent -> 'starting', no URL", s["status"] == "starting" and s["hls_url"] == "")
LIFE["live"] = True;  s = pub()
ok("encoder connected -> 'live' with HLS+DASH", s["status"] == "live" and s["hls_url"] == f"https://customer-abc123.cloudflarestream.com/{UID}/manifest/video.m3u8" and s["dash_url"].endswith("/manifest/video.mpd"), s)
blob = json.dumps(s)
ok("public JSON never leaks credentials", "SECRETKEY123" not in blob and "PASSPH456" not in blob and "rtmps" not in blob.lower())
A.KOJA_NEWS_LL_HLS = True; ok("LL-HLS flag appends protocol", pub()["hls_url"].endswith("?protocol=llhls")); A.KOJA_NEWS_LL_HLS = False

# 8 scenes / metadata / graphics
for sc in ("desk", "reporter", "interview", "world"):
    ok(f"scene {sc}", P("/api/admin/news/live/state", {"scene": sc}).status_code == 200 and pub()["scene"] == sc)
ok("unknown scene rejected", P("/api/admin/news/live/state", {"scene": "hack"}).status_code == 400)
P("/api/admin/news/live/state", {"headline": "Budget 2027 tabled", "location": "Lusaka", "category": "Politics", "presenter": "Jane"})
s = pub(); ok("metadata reaches viewers", (s["headline"], s["location"], s["category"], s["presenter"]) == ("Budget 2027 tabled", "Lusaka", "Politics", "Jane"))
ok("breaking needs text", P("/api/admin/news/live/state", {"breaking_enabled": True}).status_code == 400)
P("/api/admin/news/live/state", {"breaking_text": "Major announcement", "breaking_enabled": True})
s = pub(); ok("breaking banner on air", s["breaking"] == {"enabled": True, "text": "Major announcement"})
ok("lower third needs a name", P("/api/admin/news/live/state", {"lower_third_enabled": True}).status_code == 400)
P("/api/admin/news/live/state", {"lower_third_name": "Jane Phiri", "lower_third_title": "Political Editor", "lower_third_enabled": True})
ok("lower third on air", pub()["lower_third"]["name"] == "Jane Phiri")
P("/api/admin/news/live/state", {"ticker_items": "\n".join(f"item {i}" for i in range(15)) + "\n" + "x" * 400, "ticker_enabled": True})
t = pub()["ticker"]; ok("ticker capped at 12 items, 160 chars", t["enabled"] and len(t["items"]) == 12 and all(len(i) <= 160 for i in t["items"]))
ok("http logo rejected", P("/api/admin/news/live/state", {"logo_url": "http://evil/x.png"}).status_code == 400)
ok("javascript: logo rejected", P("/api/admin/news/live/state", {"logo_url": "javascript:alert(1)"}).status_code == 400)
ok("https logo accepted", P("/api/admin/news/live/state", {"logo_url": "https://cdn.example.com/l.png"}).status_code == 200 and pub()["logo"]["url"].startswith("https://"))

# 9 mass-assignment: producer cannot overwrite server-controlled fields
P("/api/admin/news/live/state", {"cf_input_uid": "b" * 32, "on_air": False, "started_at": "x", "id": "other"})
st = A._news_state_load(); ok("server-controlled fields ignored", st["cf_input_uid"] == UID and st["on_air"] is True and st["id"] == "main")

# 10 XSS: stored text is escaped in page boot JSON
P("/api/admin/news/live/state", {"headline": "</script><script>alert(1)</script>"})
r = c.get("/admin/news/live"); ok("script injection escaped in studio page", b"</script><script>alert(1)" not in r.data)

# 11 caching: 30 viewers polling -> at most 1 DB read
A._news_cache_clear(); CALLS["first_row"] = 0
for _ in range(30): c.get("/api/news/live/state")
ok("30 viewer polls -> <=1 DB read (cached)", CALLS["first_row"] <= 1, CALLS["first_row"])

# 12 attach
ok("attach bad id rejected", P("/api/admin/news/live/attach", {"uid": "nope"}).status_code == 400)
ok("attach unknown id -> 404", P("/api/admin/news/live/attach", {"uid": "c" * 32}).status_code == 404)

# 13 end broadcast clears time-sensitive graphics
r = P("/api/admin/news/live/end"); st = r.get_json()["state"]
ok("end: off air, breaking+lower third cleared", st["on_air"] is False and not st["breaking_enabled"] and not st["lower_third_enabled"])
s = pub(); ok("viewers see offline, no stream url", s["status"] == "offline" and s["hls_url"] == "")

# 14 audit log
kinds = [e["kind"] for e in DB.get("koja_news_live_events", [])]
ok("audit log has provision/go_live/end", {"provision", "go_live", "end"} <= set(kinds), kinds)

# 15 manual HLS fallback (no Cloudflare)
DB.clear(); A._cache = None; A.CF_ACCOUNT_ID = ""; A._CF_CUSTOMER_RAW = ""
ok("manual HLS must be https", P("/api/admin/news/live/state", {"manual_hls_url": "http://x/a.m3u8"}).status_code == 400)
P("/api/admin/news/live/state", {"manual_hls_url": "https://stream.example.com/live/index.m3u8"})
ok("manual HLS go-live works", P("/api/admin/news/live/go-live").status_code == 200)
s = pub(); ok("manual HLS served as live", s["status"] == "live" and s["hls_url"] == "https://stream.example.com/live/index.m3u8")
print(f"\n{sum(res)}/{len(res)} passed")

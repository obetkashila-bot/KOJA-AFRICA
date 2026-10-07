import os, sys, json, uuid
os.environ.update(SECRET_KEY="test-secret-key-123456", SUPABASE_URL="https://x.supabase.co",
                  SUPABASE_SECRET_KEY="k", SITE_URL="http://localhost", SESSION_COOKIE_SECURE="false")
sys.path.insert(0, ".")
import app as A

# ---- fake consent table (honours any filter the code sends, like the real DB) ----
TERMS, TERMS_CALLS, TABLE = {}, [], {"up": True}
class Resp:
    def __init__(s, code, data): s.status_code, s._d, s.ok, s.text = code, data, 200 <= code < 300, json.dumps(data)
    def json(s): return s._d
_orig_get = A.requests.get
def f_get(url, headers=None, params=None, timeout=None, **kw):
    if "koja_terms_acceptances" in url:
        TERMS_CALLS.append(1)
        if not TABLE["up"]: return Resp(404, {"message": "relation does not exist"})
        uid = (params or {})["user_id"].replace("eq.", "")
        rows = [r for r in TERMS.get(uid, []) if r["accepted"]]
        if "terms_version" in (params or {}):                      # would exclude older versions
            rows = [r for r in rows if r["terms_version"] == params["terms_version"].replace("eq.", "")]
        return Resp(200, rows[:1])
    raise A.requests.exceptions.ConnectionError("offline")
A.requests.get = f_get

# ---- fake app DB ----
DB = {}
def _m(r, f): return all(str(r.get(k)) == str(v) for k, v in (f or {}).items())
def f_select(t, filters=None, select="*", order=None, limit=None): return [dict(r) for r in DB.get(t, []) if _m(r, filters)][: (limit or 10**6)]
def f_insert(t, p, returning="representation"):
    row = json.loads(json.dumps(p, default=str)); row.setdefault("id", str(uuid.uuid4()))
    if t == "koja_terms_acceptances": TERMS.setdefault(row["user_id"], []).append(row)
    DB.setdefault(t, []).append(row); return dict(row), None
def f_update(t, f, p):
    hit = [r for r in DB.get(t, []) if _m(r, f)]; [r.update(p) for r in hit]; return [dict(r) for r in hit], None
A.db_select, A.db_insert, A.db_update = f_select, f_insert, f_update
A.first_row = lambda t, f: (f_select(t, f, limit=1) or [None])[0]

def user(i, **kw): return dict({"id": "u-" + i, "full_name": i, "email": i + "@t.com", "role": "student", "is_admin": False, "is_active": True}, **kw)
OLD, NEW = user("old"), user("new")           # OLD accepted under an older version; NEW has no record at all
TERMS["u-old"] = [{"user_id": "u-old", "terms_version": "2025-01-01-v0", "accepted": True, "created_at": "2025-01-01"}]
WHO = {"u": OLD}
A.current_user = lambda: WHO["u"]
A.app.config["TESTING"] = True; A.app.config["PROPAGATE_EXCEPTIONS"] = False
c = A.app.test_client()
with c.session_transaction() as s: s["_csrf_token"] = "tok"
res = []
def ok(name, cond, extra=""):
    print(("PASS" if cond else "FAIL"), "-", name, ("" if cond else "   " + str(extra)[:250])); res.append(bool(cond)); return cond
post = lambda url, data=None: c.post(url, data=dict(data or {}, _csrf_token="tok"))
loc = lambda r: (r.headers.get("Location") or "")

# 1. accepted at account creation (older version string) -> Music works end to end
WHO["u"] = OLD; n = len(TERMS_CALLS)
r = c.get("/music/artist/new"); ok("accepted user (older version) opens artist registration", r.status_code == 200, (r.status_code, loc(r)))
post("/music/artist/new", {"artist_name": "Old Timer", "country": "Zambia", "genre": "Gospel", "bio": "b"})
ok("artist profile created", any(a["artist_name"] == "Old Timer" for a in DB.get("koja_music_artists", [])))
r = c.get("/music/studio"); ok("accepted user enters MUSIC Studio", r.status_code == 200, (r.status_code, loc(r)))
ok("no consent lookups happened inside the services", len(TERMS_CALLS) == n, len(TERMS_CALLS) - n)

# 2. user with NO consent record: services never bounce them to /terms
WHO["u"] = NEW; n = len(TERMS_CALLS)
r = c.get("/music/artist/new"); ok("no-record user is not bounced to /terms in a service", r.status_code == 200 and "/terms" not in loc(r), (r.status_code, loc(r)))
r = c.get("/music/studio"); ok("non-artist opening Studio is sent to artist registration (not 403, not /terms)", r.status_code == 302 and loc(r).endswith("/music/artist/new"), (r.status_code, loc(r)))
post("/music/artist/new", {"artist_name": "Fresh Voice", "country": "Kenya", "genre": "Afrobeats"})
r = c.get("/music/studio"); ok("after registering, Studio opens", r.status_code == 200, (r.status_code, loc(r)))
for path in ("/business", "/music/artist/new", "/business/connect-plus/investors"):
    r = c.get(path); ok(f"other services don't re-ask consent: {path}", "/terms" not in loc(r) and r.status_code in (200, 302), (r.status_code, loc(r)))
ok("zero consent lookups across all those service requests", len(TERMS_CALLS) == n, len(TERMS_CALLS) - n)

# 3. non-artists can't use artist-only actions
WHO["u"] = user("rando")
r = post("/music/studio/upload", {"title": "x"}); ok("non-artist upload is forbidden (403)", r.status_code == 403, r.status_code)
WHO["u"] = None; r = c.get("/music/studio"); ok("anonymous is sent to login", r.status_code == 302 and "/login" in loc(r), loc(r))

# 4. the single account-level step (sign-in / first social sign-in)
WHO["u"] = OLD;  ok("older-version acceptance counts as consent", A._terms_required_for_user(OLD) is False)
ok("account with no record is asked once, at sign-in level", A._terms_required_for_user(NEW) is True)
WHO["u"] = NEW; r = post("/terms/decision", {"decision": "agree", "next": "/music/studio"})
ok("accepting records consent and returns user to where they were going", r.status_code == 302 and loc(r).endswith("/music/studio") and TERMS.get("u-new"), (r.status_code, loc(r)))
ok("after accepting, never asked again", A._terms_required_for_user(NEW) is False)
A.TERMS_VERSION = "2099-12-31-v9"
ok("a newer TERMS_VERSION does not force existing users to re-accept", A._terms_required_for_user(OLD) is False and A._terms_required_for_user(NEW) is False)
post("/terms/decision", {"decision": "agree"}); ok("new acceptances are stamped with the current version (audit trail)", TERMS["u-new"][-1]["terms_version"] == "2099-12-31-v9")

# 5. unchanged behaviours
TABLE["up"] = False; ok("consent table unavailable -> nothing is enforced", A._terms_required_for_user(user("ghost")) is False); TABLE["up"] = True
WHO["u"] = user("decliner"); r = post("/terms/decision", {"decision": "disagree"}); ok("declining still signs the user out", r.status_code == 302 and not TERMS.get("u-decliner"))
print(f"\n{sum(res)}/{len(res)} passed")

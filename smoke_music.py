import os, io, sys, types
os.environ.update(SECRET_KEY="test-secret-key-123456", SUPABASE_URL="https://x.supabase.co",
                  SUPABASE_SECRET_KEY="k", SITE_URL="http://localhost", SESSION_COOKIE_SECURE="false")
sys.path.insert(0, ".")
import app as A

# ---- in-memory fake DB ----
DB = {}
def _match(r, f): return all(str(r.get(k)) == str(v) for k, v in (f or {}).items())
def fake_select(table, filters=None, select="*", order=None, limit=None):
    return [dict(r) for r in DB.get(table, []) if _match(r, filters)][: (limit or 10**6)]
def fake_insert(table, payload, returning="representation"):
    DB.setdefault(table, []).append(dict(payload)); return [payload], None
def fake_update(table, filters, payload):
    for r in DB.get(table, []):
        if _match(r, filters): r.update(payload)
    return True, None
def fake_first(table, filters):
    rows = fake_select(table, filters, limit=1); return rows[0] if rows else None
A.db_select, A.db_insert, A.db_update, A.first_row = fake_select, fake_insert, fake_update, fake_first
A._music_optional_insert = lambda t, p: fake_insert(t, p)[1:]  and (None, None) or (None, None)
A.db_delete = lambda t, f: (DB.__setitem__(t, [r for r in DB.get(t, []) if not _match(r, f)]), None)[1]

# fake storage: record what upload_storage would send
SENT = []
class FakeResp: ok = True; text = ""
def fake_post(url, **kw):
    SENT.append((url, len(kw.get("data", b"")), kw.get("timeout"))); return FakeResp()
A.requests.post = fake_post
A.supabase_configured = lambda: True

USER = {"id": "11111111-1111-1111-1111-111111111111", "full_name": "T", "role": "student",
        "is_admin": False, "is_active": True, "email": "t@t.com"}
A.current_user = lambda: USER
A.app.config["TESTING"] = True
A.app.config["PROPAGATE_EXCEPTIONS"] = False
c = A.app.test_client()
with c.session_transaction() as s: s["_csrf_token"] = "tok"; s["user_id"] = USER["id"]
H = {"X-CSRF-Token": "tok"}
ok = lambda name, cond: print(("PASS" if cond else "FAIL"), "-", name) or cond
res = []

# 1. student (non-artist) can reach artist-creation page (was 403 before)
r = c.get("/music/artist/new"); res.append(ok("student can open /music/artist/new", r.status_code == 200))
# 2. create artist profile
r = c.post("/music/artist/new", data={"artist_name": "Test Artist", "country": "Zambia", "genre": "Afrobeat", "bio": "b", "_csrf_token": "tok"})
res.append(ok("artist profile created", len(DB.get("koja_music_artists", [])) == 1))
aid = DB["koja_music_artists"][0]["id"]
# 3. studio now accessible (profile exists -> artist user)
r = c.get("/music/studio"); res.append(ok("studio accessible after profile", r.status_code == 200))
# 4. toolbar link for non-artist
USER2 = dict(USER, id="22222222-2222-2222-2222-222222222222"); A.current_user = lambda: USER2
r = c.get("/music"); res.append(ok("'Become an Artist' link shown to non-artist", b"Become an Artist" in r.data))
A.current_user = lambda: USER

def upload(video=b"v" * 1024, audio=None, audio_name="song.mp3", extra=None):
    d = {"artist_id": aid, "title": "Song", "master_owner": "Me", "composition_owner": "Me",
         "licence_reference": "LIC-1", "_csrf_token": "tok",
         "music_video": (io.BytesIO(video), "clip.mp4")}
    if audio is not None: d["audio_file"] = (io.BytesIO(audio), audio_name)
    return c.post("/music/studio/upload", data=d, content_type="multipart/form-data")

# 5. mp3 audio accepted + track saved
before = len(DB.get("koja_music_tracks", []))
upload(audio=b"a" * 2048)
res.append(ok("video + mp3 upload saves a track", len(DB.get("koja_music_tracks", [])) == before + 1))
t = DB["koja_music_tracks"][-1]
res.append(ok("track has video_url and audio_url", bool(t.get("video_url")) and bool(t.get("audio_url"))))
# 6. 40 MB video passes (>15MB old limit)
n = len(DB["koja_music_tracks"]); upload(video=b"v" * (40 * 1024 * 1024))
res.append(ok("40 MB video accepted (old limit was 15 MB)", len(DB["koja_music_tracks"]) == n + 1))
res.append(ok("large upload used extended timeout (300s)", any(s[1] > 15*1024*1024 and s[2] == 300 for s in SENT)))
# 7. over-limit rejected cleanly (no crash, no track)
A.KOJA_MUSIC_MAX_MB = 100
n = len(DB["koja_music_tracks"]); r = upload(video=b"v" * (105 * 1024 * 1024))
res.append(ok("105 MB video rejected, no track saved", len(DB["koja_music_tracks"]) == n and r.status_code in (302, 413)))
# 8. disallowed type rejected
n = len(DB["koja_music_tracks"]); upload(audio=b"x" * 10, audio_name="evil.exe")
res.append(ok(".exe audio rejected", len(DB["koja_music_tracks"]) == n))
# 9. _music_upload never returns bare None
res.append(ok("_music_upload returns tuple when empty", A._music_upload(None, "x")[1] is not None))
# 10. public listing shows the published track
r = c.get("/music"); res.append(ok("/music lists uploaded track", b"Song" in r.data))
# 11. play/like APIs
tid = DB["koja_music_tracks"][0]["id"]
r = c.post(f"/api/music/track/{tid}/play", headers=H); res.append(ok("play API ok", r.status_code == 200))
r = c.post(f"/api/music/track/{tid}/like", headers=H); res.append(ok("like API ok", r.status_code == 200 and r.get_json().get("liked") is True))
print(f"\n{sum(res)}/{len(res)} passed")

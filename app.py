import os, math, uuid, hashlib, secrets, mimetypes, logging
from datetime import datetime, timezone
from functools import wraps
from io import BytesIO

import requests
from flask import Flask, request, redirect, url_for, session, jsonify, render_template_string, flash, send_file
from werkzeug.utils import secure_filename

# ============================================================
# KOJA AFRICA - SINGLE FILE FLASK APPLICATION
# Supabase REST + Storage, Render compatible, no psycopg.
# ============================================================

logging.basicConfig(level=logging.INFO)
app = Flask(__name__)
app.secret_key = os.getenv("KOJA_SECRET_KEY", os.getenv("SECRET_KEY", secrets.token_hex(32)))
app.config['SESSION_COOKIE_SECURE'] = os.getenv('SESSION_COOKIE_SECURE','true').lower() == 'true'
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.permanent_session_lifetime = __import__('datetime').timedelta(days=30)
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY", os.getenv("SUPABASE_SERVICE_ROLE_KEY", os.getenv("SUPABASE_PUBLISHABLE_KEY", "")))
STORAGE_BUCKET = os.getenv("KOJA_STORAGE_BUCKET", "koja-files")
ADMIN_EMAILS = {x.strip().lower() for x in os.getenv("KOJA_ADMIN_EMAILS", "admin@koja.africa").split(",") if x.strip()}

if not SUPABASE_URL or not SUPABASE_KEY:
    logging.warning("SUPABASE_URL/SUPABASE_SERVICE_KEY are not configured.")


def sb_headers(extra=None):
    h = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json"}
    if extra: h.update(extra)
    return h


def sb_request(method, table, params=None, payload=None, timeout=20, headers=None):
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None, "Supabase is not configured"
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    try:
        r = requests.request(method, url, params=params, json=payload, headers=sb_headers(headers), timeout=timeout)
        if r.status_code >= 400:
            return None, f"Supabase {r.status_code}: {r.text[:1000]}"
        if not r.text: return [], None
        try: return r.json(), None
        except Exception: return [], None
    except Exception as e:
        return None, str(e)


def sb_select(table, params=None, single=False):
    data, err = sb_request("GET", table, params=params)
    if err: return None, err
    if single: return (data[0] if data else None), None
    return data or [], None


def sb_insert(table, row, select="*"):
    return sb_request("POST", table, params={"select": select}, payload=row, headers={"Prefer": "return=representation"})


def sb_update(table, filters, row, select="*"):
    p = dict(filters); p["select"] = select
    return sb_request("PATCH", table, params=p, payload=row, headers={"Prefer": "return=representation"})


def sb_delete(table, filters):
    return sb_request("DELETE", table, params=filters, headers={"Prefer": "return=representation"})


def storage_upload(path, data, content_type):
    if not SUPABASE_URL or not SUPABASE_KEY: return None, "Supabase is not configured"
    url = f"{SUPABASE_URL}/storage/v1/object/{STORAGE_BUCKET}/{path.lstrip('/')}"
    h = {"Authorization": f"Bearer {SUPABASE_KEY}", "apikey": SUPABASE_KEY, "Content-Type": content_type, "x-upsert": "true"}
    try:
        r = requests.post(url, data=data, headers=h, timeout=30)
        if r.status_code >= 400: return None, r.text[:1000]
        return f"{SUPABASE_URL}/storage/v1/object/public/{STORAGE_BUCKET}/{path.lstrip('/')}", None
    except Exception as e: return None, str(e)


def storage_delete(path):
    if not SUPABASE_URL or not SUPABASE_KEY: return
    url = f"{SUPABASE_URL}/storage/v1/object/{STORAGE_BUCKET}"
    try:
        requests.delete(url, json={"prefixes":[path.lstrip('/')]}, headers=sb_headers(), timeout=20)
    except Exception: pass


def now_iso(): return datetime.now(timezone.utc).isoformat()


def current_user():
    # Public KOJA mode: every browser receives a stable guest UUID.
    # No login or account creation is required for customer/driver workflows.
    if not session.get("guest_id"):
        session["guest_id"] = str(uuid.uuid4())
    return session.setdefault("user", {"id": session["guest_id"], "email": "", "full_name": "Guest", "role": "customer"})


def login_required(fn):
    @wraps(fn)
    def wrapped(*a, **kw):
        current_user()
        return fn(*a, **kw)
    return wrapped


def admin_required(fn):
    @wraps(fn)
    def wrapped(*a, **kw):
        secret = os.getenv("KOJA_ADMIN_SECRET", "")
        supplied = request.args.get("admin_key", "") or request.headers.get("X-KOJA-ADMIN", "")
        if not secret or supplied != secret:
            return jsonify(error="Admin access denied. Set KOJA_ADMIN_SECRET and provide admin_key."), 403
        return fn(*a, **kw)
    return wrapped


def is_admin(u):
    return (u.get("role") == "admin") or (u.get("email", "").lower() in ADMIN_EMAILS)


def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0088
    p1, p2 = math.radians(float(lat1)), math.radians(float(lat2))
    dp = math.radians(float(lat2)-float(lat1)); dl = math.radians(float(lon2)-float(lon1))
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))


def user_profile(user_id):
    data, err = sb_select("profiles", {"id": f"eq.{user_id}", "limit":"1"}, True)
    return data or {}


def get_user_by_email(email):
    # Local profiles first. Passwords are stored as password_hash in this application.
    data, err = sb_select("profiles", {"email": f"eq.{email.lower()}", "limit":"1"}, True)
    return data


def find_driver_profile(driver_id):
    data, _ = sb_select("driver_profiles", {"id": f"eq.{driver_id}", "limit":"1"}, True)
    return data


def get_driver_for_user(user_id):
    data, _ = sb_select("driver_profiles", {"user_id": f"eq.{user_id}", "limit":"1"}, True)
    return data


def active_driver_locations():
    rows, _ = sb_select("driver_locations", {"is_online":"eq.true", "order":"created_at.desc", "limit":"500"})
    latest = {}
    now = datetime.now(timezone.utc)
    for r in rows or []:
        key = r.get("driver_id") or r.get("user_id")
        if not key or key in latest: continue
        try:
            ts = datetime.fromisoformat(str(r.get("created_at")).replace("Z", "+00:00"))
            if (now - ts).total_seconds() > 120:
                continue
        except Exception:
            pass
        latest[key] = r
    return list(latest.values())

# ------------------------------------------------------------
# Database bootstrap helper. It does not alter existing driver_profiles.
# ------------------------------------------------------------
DRIVER_LOCATION_SQL = """
create table if not exists public.driver_locations (
 id uuid primary key default gen_random_uuid(),
 driver_id uuid,
 user_id uuid,
 latitude double precision not null,
 longitude double precision not null,
 accuracy double precision,
 speed double precision,
 heading double precision,
 altitude double precision,
 is_online boolean default true,
 created_at timestamptz default now()
);
create index if not exists driver_locations_driver_id_idx on public.driver_locations(driver_id);
create index if not exists driver_locations_created_at_idx on public.driver_locations(created_at desc);
create index if not exists driver_locations_online_idx on public.driver_locations(is_online);
"""
DELIVERY_SETUP_SQL = DRIVER_LOCATION_SQL + """
create table if not exists public.deliveries (
 id uuid primary key default gen_random_uuid(),
 customer_id uuid,
 driver_id uuid,
 pickup_address text not null,
 delivery_address text not null,
 pickup_latitude double precision,
 pickup_longitude double precision,
 status text not null default 'requested',
 tracking_code text unique not null,
 created_at timestamptz default now(),
 updated_at timestamptz default now()
);
create index if not exists deliveries_driver_id_idx on public.deliveries(driver_id);
create index if not exists deliveries_customer_id_idx on public.deliveries(customer_id);
create index if not exists deliveries_tracking_code_idx on public.deliveries(tracking_code);
create index if not exists deliveries_status_idx on public.deliveries(status);
"""


# ------------------------------------------------------------
# UI
# ------------------------------------------------------------
BASE = """
<!doctype html><html><head><meta name=viewport content='width=device-width,initial-scale=1'>
<title>{{title}} · KOJA AFRICA</title><link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" crossorigin="anonymous"><script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js" integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=" crossorigin="anonymous"></script>
<style>
*{box-sizing:border-box}body{margin:0;font-family:Arial,sans-serif;background:#f4f7fb;color:#172033}nav{background:#101827;color:#fff;padding:14px 4%;display:flex;gap:14px;align-items:center;flex-wrap:wrap}nav a{color:#fff;text-decoration:none}nav .brand{font-size:21px;font-weight:800;margin-right:auto}.wrap{max-width:1150px;margin:22px auto;padding:0 15px}.hero{background:linear-gradient(135deg,#0f172a,#164e63);color:#fff;padding:32px;border-radius:20px;margin-bottom:20px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:16px}.card{background:#fff;border-radius:16px;padding:18px;box-shadow:0 5px 20px #0000000d;margin-bottom:16px}input,textarea,select{width:100%;padding:12px;border:1px solid #d5dbe5;border-radius:10px;margin:6px 0 12px}button,.btn{background:#0f766e;color:#fff;border:0;padding:11px 16px;border-radius:10px;text-decoration:none;display:inline-block;cursor:pointer}button.secondary,.btn.secondary{background:#334155}button.danger,.btn.danger{background:#b91c1c}.muted{color:#64748b}.ok{color:#15803d}.error{color:#b91c1c}.pill{display:inline-block;padding:5px 9px;border-radius:999px;background:#e2e8f0;margin:3px}.map{height:430px;border-radius:15px;background:#dbeafe;overflow:hidden}.leaflet-map{height:430px;width:100%;border-radius:15px}.row{display:flex;gap:10px;flex-wrap:wrap;align-items:center}.stat{font-size:28px;font-weight:800}.flash{padding:12px;border-radius:10px;background:#fff3cd;margin-bottom:10px}.small{font-size:13px}.driver{border:1px solid #e2e8f0;border-radius:12px;padding:12px;margin:8px 0}.table{width:100%;border-collapse:collapse}.table td,.table th{padding:9px;border-bottom:1px solid #e5e7eb;text-align:left}@media(max-width:600px){.hero{padding:22px}.map{height:350px}}
</style></head><body><nav><a class=brand href="{{url_for('home')}}">KOJA AFRICA</a><a href="{{url_for('home')}}">Home</a><a href="{{url_for('delivery')}}">Delivery</a><a href="{{url_for('assignments')}}">Assignments</a><a href="{{url_for('services')}}">Services</a><a href="{{url_for('dashboard')}}">Dashboard</a><a href="{{url_for('driver_register')}}">Become a Driver</a></nav><main class=wrap>{% with messages=get_flashed_messages() %}{% for m in messages %}<div class=flash>{{m}}</div>{% endfor %}{% endwith %}{{body|safe}}</main></body></html>
"""

def page(title, body, **ctx):
    return render_template_string(BASE, title=title, body=render_template_string(body, **ctx), user=current_user(), admin=is_admin(current_user() or {}))

# ------------------------------------------------------------
# Home / auth
# ------------------------------------------------------------
@app.route("/")
def home():
    return page("Home", """
    <section class=hero><h1>KOJA AFRICA</h1><p>Knowledge • Questions • Answers • Services • Live Delivery</p><p>No login or account creation required.</p><div class=row><a class=btn href='{{url_for("delivery")}}'>Start Delivery</a><a class='btn secondary' href='{{url_for("assignments")}}'>Assignments</a></div></section>
    <div class=grid><div class=card><h3>Live Delivery</h3><p>Find nearby online drivers, request delivery and track an accepted driver.</p></div><div class=card><h3>Academic</h3><p>Submit assignments and manage answered files.</p></div><div class=card><h3>Professional Services</h3><p>Doctors, teachers/tutors and CV support.</p></div><div class=card><h3>Business & Farmers</h3><p>Registration and service workflows in one portal.</p></div></div>
    """)

# Login and account creation are intentionally removed. KOJA uses public browser sessions.
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))

@app.route("/dashboard")
def dashboard():
    u=current_user(); d=get_driver_for_user(u["id"])
    return page("Dashboard", """<div class=hero><h2>KOJA AFRICA Dashboard</h2><p>No login required. Start a service immediately.</p></div><div class=grid><div class=card><h3>Live Delivery</h3><p>Find online drivers and track deliveries live.</p><a class=btn href='{{url_for("delivery")}}'>Start Delivery</a></div><div class=card><h3>Driver</h3>{% if driver %}<p>Status: <b>{{driver.get('status','pending')}}</b></p><a class=btn href='{{url_for("driver_panel")}}'>Driver panel</a>{% else %}<p>Register this device as a driver.</p><a class=btn href='{{url_for("driver_register")}}'>Become a Driver</a>{% endif %}</div><div class=card><h3>Assignments</h3><a class=btn href='{{url_for("assignments")}}'>Submit Assignment</a></div><div class=card><h3>Services</h3><a class=btn href='{{url_for("services")}}'>Open Services</a></div></div>""", user=u, driver=d)

# ------------------------------------------------------------
# Driver registration / GPS
# ------------------------------------------------------------
@app.route("/driver/register", methods=["GET","POST"])
@login_required
def driver_register():
    u=current_user()
    if request.method=="POST":
        row={"user_id":u["id"],"full_name":request.form.get("full_name",u.get("full_name","")),"phone":request.form.get("phone",""),"email":u.get("email"),"vehicle_type":request.form.get("vehicle_type",""),"vehicle_number":request.form.get("vehicle_number",""),"license_number":request.form.get("license_number",""),"status":"pending","is_online":False}
        # Existing schemas sometimes require an id; include one only if creating a new record.
        existing=get_driver_for_user(u["id"])
        if existing: data,err=sb_update("driver_profiles",{"id":f"eq.{existing['id']}"},row)
        else: data,err=sb_insert("driver_profiles",row)
        if err: flash("Driver registration failed: "+err)
        else: flash("Driver registration submitted.")
        return redirect(url_for("driver_panel"))
    return page("Driver registration", """<div class=card><h2>Register as a driver</h2><form method=post><label>Name</label><input name=full_name value='{{user.full_name}}' required><label>Phone</label><input name=phone><label>Vehicle type</label><input name=vehicle_type placeholder='Car, motorcycle, van'><label>Vehicle number</label><input name=vehicle_number><label>License number</label><input name=license_number><button>Submit registration</button></form></div>""", user=u)

@app.route("/driver")
@login_required
def driver_panel():
    d=get_driver_for_user(current_user()["id"])
    if not d: return redirect(url_for("driver_register"))
    return page("Driver panel", """<div class=card><h2>Driver panel</h2><p>Vehicle: {{driver.get('vehicle_type','')}} {{driver.get('vehicle_number','')}}</p><p>Approval: <b>{{driver.get('status','pending')}}</b></p>{% if driver.get('status','pending')|lower in ['approved','active'] %}<div class=row><button id=online onclick='setOnline(true)'>Go Online</button><button class=secondary onclick='setOnline(false)'>Go Offline</button></div><p id=state class=muted>GPS is waiting.</p><div id=map class='map leaflet-map'></div>{% else %}<p class=muted>Admin approval is required before accepting deliveries.</p>{% endif %}</div>
    <div class=card><h3>Incoming deliveries</h3><div id=reqs>Loading...</div></div>
    <script>
    let watch=null, online=false;
    async function setOnline(v){const r=await fetch('/api/driver/online',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({online:v})}); const j=await r.json(); if(!r.ok){alert(j.error||'Failed');return} online=v; document.getElementById('state').textContent=v?'Online — sharing GPS when permission is granted.':'Offline'; if(v) startGPS(); else if(watch!==null){navigator.geolocation.clearWatch(watch);watch=null}}
    let driverMap=null, driverMarker=null;
function initDriverMap(){ if(!driverMap){driverMap=L.map('map').setView([-15.4167,28.2833],12); L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'© OpenStreetMap'}).addTo(driverMap);} }
function startGPS(){initDriverMap();if(!navigator.geolocation){alert('This browser does not support GPS');return} watch=navigator.geolocation.watchPosition(async p=>{const c=p.coords; const r=await fetch('/api/driver/location',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({latitude:c.latitude,longitude:c.longitude,accuracy:c.accuracy,speed:c.speed,heading:c.heading,altitude:c.altitude})}); if(!r.ok){document.getElementById('state').textContent='GPS upload failed';return} if(driverMarker) driverMarker.setLatLng([c.latitude,c.longitude]); else {driverMarker=L.marker([c.latitude,c.longitude]).addTo(driverMap).bindPopup('Your live location');} driverMap.setView([c.latitude,c.longitude],15); document.getElementById('state').textContent='LIVE GPS • '+c.latitude.toFixed(6)+', '+c.longitude.toFixed(6)+' • accuracy '+Math.round(c.accuracy||0)+' m'},e=>document.getElementById('state').textContent='GPS error: '+e.message,{enableHighAccuracy:true,maximumAge:3000,timeout:15000})}
    async function loadReqs(){let r=await fetch('/api/driver/requests');let j=await r.json();let el=document.getElementById('reqs');if(!j.requests||!j.requests.length){el.innerHTML='<p class=muted>No delivery requests.</p>';return}el.innerHTML=j.requests.map(x=>{let b='';if(x.status==='requested')b='<button onclick="act(\''+x.id+'\',\'accepted\')">Accept</button> <button class=secondary onclick="act(\''+x.id+'\',\'rejected\')">Reject</button>';else if(x.status==='accepted')b='<button onclick="act(\''+x.id+'\',\'picked_up\')">Pick Up</button>';else if(x.status==='picked_up')b='<button onclick="act(\''+x.id+'\',\'in_transit\')">Start In Transit</button>';else if(x.status==='in_transit')b='<button onclick="act(\''+x.id+'\',\'delivered\')">Mark Delivered</button>';return '<div class=driver><b>'+x.tracking_code+'</b><br>'+x.pickup_address+' → '+x.delivery_address+'<br>Status: <b>'+x.status+'</b><br>'+b+'</div>'}).join('')}
    async function act(id,status){await fetch('/api/deliveries/'+id+'/status',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({status})});loadReqs()} loadReqs(); setInterval(loadReqs,7000);
    </script>""", driver=d)

@app.post("/api/driver/online")
@login_required
def driver_online():
    d=get_driver_for_user(current_user()["id"])
    if not d: return jsonify(error="Driver profile not found"),404
    if str(d.get("status","pending")).lower() not in ("approved","active"):
        return jsonify(error="Driver is not approved"),403
    online=bool(request.json.get("online"))
    _,err=sb_update("driver_profiles",{"id":f"eq.{d['id']}"},{"is_online":online})
    if err: return jsonify(error=err),500
    # Mark the latest location offline/online when possible.
    latest,_=sb_select("driver_locations",{"driver_id":f"eq.{d['id']}","order":"created_at.desc","limit":"1"},True)
    if latest: sb_update("driver_locations",{"id":f"eq.{latest['id']}"},{"is_online":online})
    return jsonify(ok=True,online=online)

@app.post("/api/driver/location")
@login_required
def driver_location():
    d=get_driver_for_user(current_user()["id"])
    if not d: return jsonify(error="Driver profile not found"),404
    try: lat=float(request.json["latitude"]); lon=float(request.json["longitude"])
    except Exception: return jsonify(error="latitude and longitude are required"),400
    if not (-90<=lat<=90 and -180<=lon<=180): return jsonify(error="Invalid coordinates"),400
    body=request.json
    row={"driver_id":d["id"],"user_id":current_user()["id"],"latitude":lat,"longitude":lon,"accuracy":body.get("accuracy"),"speed":body.get("speed"),"heading":body.get("heading"),"altitude":body.get("altitude"),"is_online":True,"created_at":now_iso()}
    data,err=sb_insert("driver_locations",row)
    if err: return jsonify(error=err),500
    sb_update("driver_profiles",{"id":f"eq.{d['id']}"},{"is_online":True})
    return jsonify(ok=True,location=row)

@app.get("/api/drivers/nearby")
@login_required
def nearby_drivers():
    try: lat=float(request.args["lat"]); lon=float(request.args["lon"]); radius=float(request.args.get("radius",20))
    except Exception: return jsonify(error="lat and lon are required"),400
    out=[]
    for loc in active_driver_locations():
        try: dist=haversine(lat,lon,loc["latitude"],loc["longitude"])
        except Exception: continue
        if dist<=radius:
            d=find_driver_profile(loc.get("driver_id")) or {}
            out.append({"driver_id":loc.get("driver_id"),"user_id":loc.get("user_id"),"latitude":loc["latitude"],"longitude":loc["longitude"],"accuracy":loc.get("accuracy"),"distance_km":round(dist,2),"name":d.get("full_name","Driver"),"vehicle_type":d.get("vehicle_type","")})
    out.sort(key=lambda x:x["distance_km"])
    return jsonify(drivers=out)

# ------------------------------------------------------------
# Delivery workflow
# ------------------------------------------------------------
DELIVERY_STATUSES={"requested","accepted","rejected","picked_up","in_transit","delivered","cancelled"}

@app.route("/delivery")
def delivery():
    return page("Delivery", """<div class=hero><h2>KOJA Live Delivery</h2><p>Use your current location to discover nearby online drivers.</p></div><div class=card><label>Pickup address</label><input id=pickup placeholder='Shop / pickup location'><label>Delivery address</label><input id=drop placeholder='Customer destination'><div class=row><button onclick='locate()'>Use Current Location</button><button class=secondary onclick='findDrivers()'>Find Nearby Drivers</button></div><p id=msg class=muted></p><div id=drivers></div></div><div class=card><h3>Live map</h3><div id=map class='map leaflet-map'></div></div><div class=card><h3>Track delivery</h3><input id=code placeholder='Enter tracking code'><button onclick='track()'>Track</button><div id=track></div></div><script>
let pos=null, chosen=null, timer=null, liveMap=null, liveMarker=null, driverMarkers=[];
function locate(){if(!navigator.geolocation){msg('GPS unavailable');return}navigator.geolocation.getCurrentPosition(p=>{pos=p.coords;if(!liveMap){liveMap=L.map('map').setView([p.coords.latitude,p.coords.longitude],14);L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'© OpenStreetMap contributors'}).addTo(liveMap);}else liveMap.setView([p.coords.latitude,p.coords.longitude],14);if(liveMarker)liveMarker.setLatLng([p.coords.latitude,p.coords.longitude]);else liveMarker=L.marker([p.coords.latitude,p.coords.longitude]).addTo(liveMap).bindPopup('Pickup location').openPopup();document.getElementById('pickup').value='Current GPS: '+p.coords.latitude.toFixed(6)+', '+p.coords.longitude.toFixed(6);msg('Location acquired.');findDrivers()},e=>msg('GPS error: '+e.message),{enableHighAccuracy:true,timeout:15000,maximumAge:5000})}
function msg(x){document.getElementById('msg').textContent=x}
async function findDrivers(){if(!pos){msg('Use Current Location first.');return}let r=await fetch('/api/drivers/nearby?lat='+pos.latitude+'&lon='+pos.longitude+'&radius=30');let j=await r.json();let el=document.getElementById('drivers');driverMarkers.forEach(m=>liveMap&&liveMap.removeLayer(m));driverMarkers=[];if(!j.drivers||!j.drivers.length){el.innerHTML='<p class=muted>No online drivers found within 30 km.</p>';return}j.drivers.forEach(d=>{if(liveMap){let m=L.marker([Number(d.latitude),Number(d.longitude)]).addTo(liveMap).bindPopup(d.name+' • '+d.distance_km+' km');driverMarkers.push(m);}});el.innerHTML=j.drivers.map(d=>'<div class=driver><b>'+d.name+'</b> · '+d.distance_km+' km<br>'+d.vehicle_type+'<br><button onclick="choose(\''+d.driver_id+'\',\''+d.name.replace(/\'/g,"\\'")+"\')">Select driver</button></div>').join('')}
function choose(id,name){chosen=id;document.getElementById('drivers').insertAdjacentHTML('afterbegin','<p class=ok>Selected driver: <b>'+name+'</b></p><button onclick="requestDelivery()">Request Delivery</button>')}
async function requestDelivery(){if(!chosen){msg('Select a driver first');return}let r=await fetch('/api/deliveries',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({driver_id:chosen,pickup_address:document.getElementById('pickup').value,delivery_address:document.getElementById('drop').value,pickup_latitude:pos.latitude,pickup_longitude:pos.longitude})});let j=await r.json();if(!r.ok){alert(j.error||'Request failed');return}document.getElementById('code').value=j.tracking_code;document.getElementById('track').innerHTML='<p class=ok>Delivery requested. Tracking code: <b>'+j.tracking_code+'</b></p>';startTrack(j.tracking_code)}
async function track(){startTrack(document.getElementById('code').value.trim())}
let liveMap=null, liveMarker=null;
function startTrack(code){if(!code)return;if(timer)clearInterval(timer);if(!liveMap){liveMap=L.map('map').setView([-15.4167,28.2833],12);L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'© OpenStreetMap contributors'}).addTo(liveMap);}async function x(){let r=await fetch('/api/deliveries/track/'+encodeURIComponent(code));let j=await r.json();let el=document.getElementById('track');if(!r.ok){el.innerHTML='<p class=error>'+j.error+'</p>';return}el.innerHTML='<p><b>Status:</b> '+j.delivery.status+'<br><b>Driver:</b> '+(j.driver?.name||'Assigned')+'</p>';if(j.location){const ll=[Number(j.location.latitude),Number(j.location.longitude)];if(liveMarker)liveMarker.setLatLng(ll);else liveMarker=L.marker(ll).addTo(liveMap).bindPopup('KOJA Driver');liveMap.setView(ll,15);}}x();timer=setInterval(x,3000)}
</script>""")

@app.post("/api/deliveries")
@login_required
def create_delivery():
    b=request.get_json(silent=True) or {}; uid=current_user()["id"]
    required=["driver_id","pickup_address","delivery_address"]
    if any(not b.get(k) for k in required): return jsonify(error="driver_id, pickup_address and delivery_address are required"),400
    d=find_driver_profile(b["driver_id"])
    if not d: return jsonify(error="Driver not found"),404
    row={"id":str(uuid.uuid4()),"customer_id":uid,"driver_id":b["driver_id"],"pickup_address":b["pickup_address"],"delivery_address":b["delivery_address"],"pickup_latitude":b.get("pickup_latitude"),"pickup_longitude":b.get("pickup_longitude"),"status":"requested","tracking_code":"KOJA-"+secrets.token_hex(4).upper(),"created_at":now_iso(),"updated_at":now_iso()}
    data,err=sb_insert("deliveries",row)
    if err:
        # A schema-tolerant fallback for deployments using delivery_requests.
        row.pop("updated_at",None); data,err=sb_insert("delivery_requests",row)
    if err:return jsonify(error=err),500
    return jsonify(ok=True,delivery=(data[0] if isinstance(data,list) and data else row),tracking_code=row["tracking_code"])

@app.get("/api/driver/requests")
@login_required
def driver_requests():
    d=get_driver_for_user(current_user()["id"])
    if not d:return jsonify(requests=[])
    rows,err=sb_select("deliveries",{"driver_id":f"eq.{d['id']}","status":"in.(requested,accepted,picked_up,in_transit)","order":"created_at.desc","limit":"50"})
    if err:return jsonify(error=err),500
    return jsonify(requests=rows or [])

@app.post("/api/deliveries/<delivery_id>/status")
@login_required
def delivery_status(delivery_id):
    b=request.get_json(silent=True) or {}; status=b.get("status")
    if status not in DELIVERY_STATUSES:return jsonify(error="Invalid status"),400
    d=find_driver_profile_for_delivery(delivery_id)
    u=current_user(); allowed=False
    if d and d.get("user_id")==u["id"]: allowed=True
    if is_admin(u): allowed=True
    delivery_row=get_delivery(delivery_id)
    if delivery_row and delivery_row.get("customer_id")==u["id"] and status in ("cancelled",): allowed=True
    if not allowed:return jsonify(error="Not authorised"),403
    old_status = (delivery_row or {}).get("status", "requested")
    transitions = {"requested":{"accepted","rejected","cancelled"},"accepted":{"picked_up","cancelled"},"picked_up":{"in_transit"},"in_transit":{"delivered"},"rejected":set(),"delivered":set(),"cancelled":set()}
    if status not in transitions.get(old_status, set()):
        return jsonify(error=f"Cannot change delivery from {old_status} to {status}"),409
    data,err=sb_update("deliveries",{"id":f"eq.{delivery_id}"},{"status":status,"updated_at":now_iso()})
    if err:
        data,err=sb_update("delivery_requests",{"id":f"eq.{delivery_id}"},{"status":status})
    if err:return jsonify(error=err),500
    return jsonify(ok=True,status=status)


def get_delivery(delivery_id):
    x,_=sb_select("deliveries",{"id":f"eq.{delivery_id}","limit":"1"},True)
    return x


def find_driver_profile_for_delivery(delivery_id):
    x=get_delivery(delivery_id)
    if not x:return None
    return find_driver_profile(x.get("driver_id"))

@app.get("/api/deliveries/track/<tracking_code>")
def track_delivery(tracking_code):
    x,_=sb_select("deliveries",{"tracking_code":f"eq.{tracking_code}","limit":"1"},True)
    if not x:
        x,_=sb_select("delivery_requests",{"tracking_code":f"eq.{tracking_code}","limit":"1"},True)
    if not x:return jsonify(error="Tracking code not found"),404
    d=find_driver_profile(x.get("driver_id")) or {}
    loc,_=sb_select("driver_locations",{"driver_id":f"eq.{x.get('driver_id')}","order":"created_at.desc","limit":"1"},True)
    return jsonify(delivery=x,driver={"name":d.get("full_name"),"vehicle_type":d.get("vehicle_type")},location=loc)

# ------------------------------------------------------------
# Assignments / answers / files
# ------------------------------------------------------------
@app.route("/assignments", methods=["GET","POST"])
@login_required
def assignments():
    if request.method=="POST":
        f=request.files.get("file"); q=request.form.get("question","").strip(); subject=request.form.get("subject","").strip()
        if not q:return page("Assignments","<div class=card><p class=error>Question is required.</p></div>")
        file_url=None; file_path=None
        if f and f.filename:
            name=secure_filename(f.filename); path=f"assignments/{current_user()['id']}/{uuid.uuid4()}-{name}"; content=f.read();
            file_url,err=storage_upload(path,content,f.mimetype or "application/octet-stream")
            if err: flash("File upload failed: "+err); return redirect(url_for("assignments"))
            file_path=path
        row={"id":str(uuid.uuid4()),"student_id":current_user()["id"],"question":q,"subject":subject,"file_name":f.filename if f else None,"file_path":file_path,"file_url":file_url,"status":"submitted","created_at":now_iso()}
        data,err=sb_insert("assignments",row)
        if err:flash("Assignment saving failed: "+err)
        else:flash("Assignment submitted successfully.")
        return redirect(url_for("assignments"))
    rows,_=sb_select("assignments",{"student_id":f"eq.{current_user()['id']}","order":"created_at.desc","limit":"50"})
    return page("Assignments", """<div class=card><h2>Submit assignment</h2><form method=post enctype=multipart/form-data><label>Subject</label><input name=subject><label>Question / assignment</label><textarea name=question rows=7 required></textarea><label>File</label><input type=file name=file><button>Submit</button></form></div><div class=card><h3>My submissions</h3>{% for x in rows %}<div class=driver><b>{{x.get('subject','')}}</b><br>{{x.get('question','')[:300]}}<br>Status: {{x.get('status','submitted')}}{% if x.get('answer_file_url') %}<br><a href='{{x.answer_file_url}}' target=_blank>Download answered file</a>{% endif %}</div>{% else %}<p class=muted>No submissions yet.</p>{% endfor %}</div>""", rows=rows or [])

# ------------------------------------------------------------
# Services: doctors, tutors, CV, university, farmers
# ------------------------------------------------------------
@app.route("/services")
def services():
    return page("Services", """<div class=hero><h2>KOJA Services</h2><p>Professional and community services.</p></div><div class=grid><div class=card><h3>Doctors</h3><a class=btn href='{{url_for("doctors")}}'>Doctor profiles</a></div><div class=card><h3>Teachers / Tutors</h3><a class=btn href='{{url_for("tutors")}}'>Find tutors</a></div><div class=card><h3>CV Builder</h3><a class=btn href='{{url_for("cv")}}'>Build CV</a></div><div class=card><h3>University</h3><a class=btn href='{{url_for("university")}}'>Programmes & requirements</a></div><div class=card><h3>Farmers</h3><a class=btn href='{{url_for("farmer")}}'>Register farmer</a></div></div>""")

@app.route("/doctors")
def doctors():
    rows,_=sb_select("doctor_profiles",{"is_active":"eq.true","order":"created_at.desc","limit":"100"})
    return page("Doctors", """<div class=card><h2>Doctor profiles</h2>{% for x in rows %}<div class=driver><b>{{x.get('full_name','Doctor')}}</b><br>{{x.get('specialty',x.get('specialisation',''))}}<br>{{x.get('location','')}}<br><a class=btn href='{{url_for("book_service",service="doctor",provider_id=x.get("id"))}}'>Book</a></div>{% else %}<p class=muted>No doctor profiles published.</p>{% endfor %}</div>""", rows=rows or [])

@app.route("/tutors")
def tutors():
    rows,_=sb_select("teacher_profiles",{"is_active":"eq.true","order":"created_at.desc","limit":"100"})
    return page("Teachers / Tutors", """<div class=card><h2>Teachers & tutors</h2>{% for x in rows %}<div class=driver><b>{{x.get('full_name','Teacher')}}</b><br>{{x.get('subject','')}}<br>{{x.get('location','')}}<br><a class=btn href='{{url_for("book_service",service="tutor",provider_id=x.get("id"))}}'>Book</a></div>{% else %}<p class=muted>No tutors published.</p>{% endfor %}</div>""", rows=rows or [])

@app.route("/book/<service>/<provider_id>", methods=["GET","POST"])
@login_required
def book_service(service,provider_id):
    if request.method=="POST":
        row={"id":str(uuid.uuid4()),"customer_id":current_user()["id"],"provider_id":provider_id,"service_type":service,"booking_date":request.form.get("booking_date"),"notes":request.form.get("notes"),"status":"pending","created_at":now_iso()}
        data,err=sb_insert("professional_bookings",row)
        if err:flash("Booking failed: "+err)
        else:flash("Booking submitted.")
        return redirect(url_for("dashboard"))
    return page("Booking", """<div class=card><h2>Book {{service}}</h2><form method=post><label>Date/time</label><input type=datetime-local name=booking_date required><label>Notes</label><textarea name=notes></textarea><button>Submit booking</button></form></div>""",service=service,provider_id=provider_id)

@app.route("/cv",methods=["GET","POST"])
@login_required
def cv():
    if request.method=="POST":
        row={"id":str(uuid.uuid4()),"user_id":current_user()["id"],"full_name":request.form.get("full_name"),"phone":request.form.get("phone"),"email":request.form.get("email"),"summary":request.form.get("summary"),"education":request.form.get("education"),"experience":request.form.get("experience"),"skills":request.form.get("skills"),"created_at":now_iso()}
        data,err=sb_insert("cvs",row)
        if err:flash("CV could not be saved: "+err)
        else:flash("CV saved.")
        return redirect(url_for("cv"))
    return page("CV Builder", """<div class=card><h2>CV Builder</h2><form method=post><input name=full_name value='{{user.full_name}}' placeholder='Full name' required><input name=phone placeholder='Phone'><input name=email value='{{user.email}}' placeholder='Email'><textarea name=summary placeholder='Professional summary'></textarea><textarea name=education placeholder='Education'></textarea><textarea name=experience placeholder='Experience'></textarea><textarea name=skills placeholder='Skills'></textarea><button>Save CV</button></form></div>""")

@app.route("/university")
def university():
    rows,_=sb_select("university_programmes",{"is_active":"eq.true","order":"university.asc","limit":"200"})
    return page("University", """<div class=card><h2>University → Programme → Academic year → Intake → Requirements</h2>{% for x in rows %}<div class=driver><b>{{x.get('university','University')}}</b><br>{{x.get('programme','Programme')}}<br>Year: {{x.get('academic_year','')}} · Intake: {{x.get('intake','')}}<br>{{x.get('requirements','')}}</div>{% else %}<p class=muted>No programme data has been published yet.</p>{% endfor %}</div>""", rows=rows or [])

@app.route("/farmer",methods=["GET","POST"])
@login_required
def farmer():
    if request.method=="POST":
        row={"id":str(uuid.uuid4()),"user_id":current_user()["id"],"full_name":request.form.get("full_name"),"phone":request.form.get("phone"),"farm_location":request.form.get("farm_location"),"crops":request.form.get("crops"),"created_at":now_iso()}
        data,err=sb_insert("farmers",row)
        if err:flash("Farmer registration failed: "+err)
        else:flash("Farmer registration submitted.")
        return redirect(url_for("farmer"))
    return page("Farmer registration", """<div class=card><h2>Farmer registration</h2><form method=post><input name=full_name value='{{user.full_name}}' required><input name=phone placeholder='Phone'><input name=farm_location placeholder='Farm location'><textarea name=crops placeholder='Crops / farming activities'></textarea><button>Register</button></form></div>""")

# ------------------------------------------------------------
# Admin
# ------------------------------------------------------------
@app.route("/admin")
@admin_required
def admin():
    tables=["profiles","driver_profiles","driver_locations","deliveries","assignments","professional_bookings","farmers"]
    counts={}
    for t in tables:
        x,_=sb_select(t,{"select":"id","limit":"1000"}); counts[t]=len(x or [])
    drivers,_=sb_select("driver_profiles",{"order":"created_at.desc","limit":"100"})
    return page("Admin", """<div class=hero><h2>Admin dashboard</h2></div><div class=grid>{% for k,v in counts.items() %}<div class=card><div class=stat>{{v}}</div><div>{{k}}</div></div>{% endfor %}</div><div class=card><h3>Driver approvals</h3><table class=table><tr><th>Name</th><th>Vehicle</th><th>Status</th><th>Action</th></tr>{% for d in drivers %}<tr><td>{{d.get('full_name','')}}</td><td>{{d.get('vehicle_type','')}} {{d.get('vehicle_number','')}}</td><td>{{d.get('status','pending')}}</td><td>{% if d.get('status')!='approved' %}<form method=post action='{{url_for("approve_driver",driver_id=d.get("id"))}}'><button>Approve</button></form>{% endif %}</td></tr>{% endfor %}</table></div>""", counts=counts,drivers=drivers or [])

@app.post("/admin/driver/<driver_id>/approve")
@admin_required
def approve_driver(driver_id):
    data,err=sb_update("driver_profiles",{"id":f"eq.{driver_id}"},{"status":"approved"})
    if err:flash("Approval failed: "+err)
    else:flash("Driver approved.")
    return redirect(url_for("admin"))

# ------------------------------------------------------------
# Health / setup
# ------------------------------------------------------------
@app.get("/health")
def health():
    return jsonify(status="ok",service="KOJA AFRICA",mode="public-live",live_gps=True,time=now_iso(),supabase_configured=bool(SUPABASE_URL and SUPABASE_KEY))

@app.get("/setup/driver-sql")
def driver_sql():
    # Convenient page for copying the required SQL. It does not execute SQL through REST.
    return "<pre style='white-space:pre-wrap'>"+DELIVERY_SETUP_SQL.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")+"</pre>"

@app.errorhandler(413)
def too_large(e): return "File too large. Maximum upload size is 20 MB.",413

@app.errorhandler(Exception)
def handle_error(e):
    logging.exception("Unhandled error")
    if request.path.startswith("/api/"): return jsonify(error="Internal server error"),500
    return "Internal server error. Check Render logs.",500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT","10000")), debug=False)

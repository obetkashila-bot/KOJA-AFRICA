import os
import io
import uuid
import math
import secrets
import logging
from datetime import datetime, timezone, timedelta
from functools import wraps
from urllib.parse import quote

import requests
from dotenv import load_dotenv
from flask import (
    Flask, request, redirect, url_for, session,
    render_template_string, flash, send_file, jsonify, abort
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

# ============================================================
# KOJA AFRICA
# Knowledge • Questions • Answers
#
# Complete single-file Flask application
# Flask + Supabase REST + Supabase Storage
#
# Important:
# - No psycopg / psycopg2
# - No mandatory ReportLab dependency
# - No database connection at startup
# - Works with existing KOJA tables where possible
# - Driver GPS uses public.driver_locations
# - Customer can find nearby online drivers
# - Customer can select a driver and send a delivery request
# - Driver can accept/reject and share live GPS
# ============================================================

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("koja-africa")

app = Flask(__name__)
app.secret_key = os.getenv(
    "SECRET_KEY",
    os.getenv("FLASK_SECRET_KEY", secrets.token_hex(32))
)
app.config["MAX_CONTENT_LENGTH"] = 15 * 1024 * 1024

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_KEY = (
    os.getenv("SUPABASE_SERVICE_KEY", "")
    or os.getenv("SUPABASE_KEY", "")
)
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")

STORAGE_BUCKET = os.getenv(
    "SUPABASE_STORAGE_BUCKET",
    "koja-files"
)

APP_NAME = "KOJA AFRICA"
APP_TAGLINE = "Knowledge • Questions • Answers"
MAX_UPLOAD_MB = 15

# Google Search & Distribution
SITE_URL = os.getenv("SITE_URL", "https://koja-africa.onrender.com").rstrip("/")
GSC_SITE_URL = os.getenv("GSC_SITE_URL", SITE_URL)
GSC_SERVICE_ACCOUNT_JSON = os.getenv("GSC_SERVICE_ACCOUNT_JSON", "").strip()


ALLOWED_EXTENSIONS = {
    "pdf", "doc", "docx", "txt",
    "jpg", "jpeg", "png", "webp"
}

# ============================================================
# GENERAL HELPERS
# ============================================================

def utc_now():
    return datetime.now(timezone.utc).isoformat()

def supabase_configured():
    return bool(SUPABASE_URL and SUPABASE_SERVICE_KEY)

def sb_headers(extra=None, auth_key=None):
    key = auth_key or SUPABASE_SERVICE_KEY
    h = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    if extra:
        h.update(extra)
    return h

def sb_rest_url(table):
    return f"{SUPABASE_URL}/rest/v1/{quote(table, safe='')}"

def sb_storage_url(path):
    return (
        f"{SUPABASE_URL}/storage/v1/object/"
        f"{quote(STORAGE_BUCKET, safe='')}/"
        f"{quote(path, safe='/')}"
    )

def json_or_empty(response):
    try:
        return response.json()
    except Exception:
        return {}

def clean(value):
    return str(value or "").strip()

def first_nonempty(*values):
    for value in values:
        if value is not None and str(value).strip():
            return value
    return ""

# ============================================================
# SUPABASE REST
# ============================================================

def db_select(table, filters=None, select="*", order=None, limit=None):
    if not supabase_configured():
        logger.error("Supabase is not configured.")
        return []

    params = {"select": select}
    if filters:
        for key, value in filters.items():
            if value is None:
                params[key] = "is.null"
            elif isinstance(value, str) and value.startswith(("eq.", "neq.", "gt.", "gte.", "lt.", "lte.", "in.", "is.", "like.", "ilike.")):
                params[key] = value
            else:
                params[key] = f"eq.{value}"

    if order:
        params["order"] = order
    if limit:
        params["limit"] = str(limit)

    try:
        r = requests.get(
            sb_rest_url(table),
            headers=sb_headers(),
            params=params,
            timeout=20,
        )
        if not r.ok:
            logger.error(
                "SELECT %s failed: %s %s",
                table, r.status_code, r.text[:1000]
            )
            return []
        data = json_or_empty(r)
        return data if isinstance(data, list) else []
    except Exception as exc:
        logger.exception("SELECT error: %s", exc)
        return []

def db_insert(table, payload, returning="representation"):
    if not supabase_configured():
        return None, "Supabase is not configured."

    try:
        r = requests.post(
            sb_rest_url(table),
            headers=sb_headers({"Prefer": f"return={returning}"}),
            json=payload,
            timeout=20,
        )
        if not r.ok:
            logger.error(
                "INSERT %s failed: %s %s",
                table, r.status_code, r.text[:1800]
            )
            return None, r.text
        data = json_or_empty(r)
        if isinstance(data, list):
            return (data[0] if data else None), None
        return data, None
    except Exception as exc:
        logger.exception("INSERT error: %s", exc)
        return None, str(exc)

def db_update(table, filters, payload):
    if not supabase_configured():
        return None, "Supabase is not configured."

    params = {}
    for key, value in filters.items():
        params[key] = f"eq.{value}"

    try:
        r = requests.patch(
            sb_rest_url(table),
            headers=sb_headers({"Prefer": "return=representation"}),
            params=params,
            json=payload,
            timeout=20,
        )
        if not r.ok:
            logger.error(
                "UPDATE %s failed: %s %s",
                table, r.status_code, r.text[:1800]
            )
            return None, r.text
        return json_or_empty(r), None
    except Exception as exc:
        logger.exception("UPDATE error: %s", exc)
        return None, str(exc)

def db_delete(table, filters):
    if not supabase_configured():
        return False, "Supabase is not configured."

    params = {}
    for key, value in filters.items():
        params[key] = f"eq.{value}"

    try:
        r = requests.delete(
            sb_rest_url(table),
            headers=sb_headers(),
            params=params,
            timeout=20,
        )
        if not r.ok:
            return False, r.text
        return True, None
    except Exception as exc:
        logger.exception("DELETE error: %s", exc)
        return False, str(exc)

def table_exists(table):
    if not supabase_configured():
        return False
    try:
        r = requests.get(
            sb_rest_url(table),
            headers=sb_headers(),
            params={"select": "*", "limit": "1"},
            timeout=10,
        )
        return r.status_code < 400
    except Exception:
        return False

def first_row(table, filters):
    rows = db_select(table, filters=filters, limit=1)
    return rows[0] if rows else None

# ============================================================
# AUTHENTICATION
# ============================================================

def current_user():
    return session.get("user")

def login_user(user, auth_session=None):
    session.clear()
    session["user"] = {
        "id": str(user.get("id")),
        "name": first_nonempty(
            user.get("full_name"),
            user.get("name"),
            user.get("email"),
            "KOJA User"
        ),
        "email": user.get("email"),
        "phone": user.get("phone"),
        "role": user.get("role") or "student",
        "is_admin": bool(user.get("is_admin", False)),
        "institution": user.get("institution"),
        "student_number": user.get("student_number"),
        "vehicle_type": user.get("vehicle_type"),
        "vehicle_number": user.get("vehicle_number"),
    }
    if auth_session:
        session["supabase_access_token"] = auth_session.get("access_token")
        session["supabase_refresh_token"] = auth_session.get("refresh_token")
    session.permanent = True

def find_user_by_email(email):
    email = clean(email).lower()
    if not email:
        return None

    for table in ("profiles", "koja_users", "users", "KOJA ZM"):
        rows = db_select(table, filters={"email": email}, limit=1)
        if rows:
            return rows[0]
    return None

def find_user_by_id(user_id):
    if not user_id:
        return None
    for table in ("profiles", "koja_users", "users", "KOJA ZM"):
        rows = db_select(table, filters={"id": user_id}, limit=1)
        if rows:
            return rows[0]
    return None

def password_matches(user, password):
    stored = first_nonempty(
        user.get("password_hash"),
        user.get("encrypted_password")
    )
    if not stored or not password:
        return False
    try:
        return check_password_hash(stored, password)
    except Exception:
        return False

def supabase_auth_login(email, password):
    """ Optional compatibility path for accounts created in Supabase Auth. Set SUPABASE_ANON_KEY in Render for this path. """
    if not SUPABASE_URL:
        return None

    key = SUPABASE_ANON_KEY or SUPABASE_SERVICE_KEY
    if not key:
        return None

    try:
        r = requests.post(
            f"{SUPABASE_URL}/auth/v1/token",
            params={"grant_type": "password"},
            headers={
                "apikey": key,
                "Content-Type": "application/json",
            },
            json={"email": email, "password": password},
            timeout=20,
        )
        if not r.ok:
            logger.warning(
                "Supabase Auth password login failed: %s %s",
                r.status_code, r.text[:500]
            )
            return None
        return json_or_empty(r)
    except Exception as exc:
        logger.exception("Supabase Auth login error: %s", exc)
        return None

def create_local_profile(user_id, email, full_name="", phone=""):
    payload = {
        "id": str(user_id),
        "email": email,
        "full_name": full_name or email,
        "name": full_name or email,
        "phone": phone or None,
        "role": "student",
        "is_admin": False,
        "is_active": True,
    }
    row, error = db_insert("profiles", payload)
    return row or payload, error

# ============================================================
# STORAGE
# ============================================================

def upload_storage(file_storage, folder="uploads"):
    if not file_storage or not file_storage.filename:
        return None, "No file supplied."
    if not supabase_configured():
        return None, "Supabase is not configured."

    filename = secure_filename(file_storage.filename)
    if not filename:
        return None, "Invalid filename."

    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        return None, f"File type .{ext} is not allowed."

    data = file_storage.read()
    if len(data) > MAX_UPLOAD_MB * 1024 * 1024:
        return None, f"Maximum file size is {MAX_UPLOAD_MB} MB."

    path = f"{folder.strip('/')}/{uuid.uuid4().hex}_{filename}"
    mime = file_storage.mimetype or "application/octet-stream"

    try:
        r = requests.post(
            sb_storage_url(path),
            headers=sb_headers({
                "Content-Type": mime,
                "x-upsert": "true",
            }),
            data=data,
            timeout=60,
        )
        if not r.ok:
            return None, r.text[:1200]

        public_url = (
            f"{SUPABASE_URL}/storage/v1/object/public/"
            f"{quote(STORAGE_BUCKET, safe='')}/"
            f"{quote(path, safe='/')}"
        )
        return {
            "path": path,
            "url": public_url,
            "file_name": filename,
            "file_size": len(data),
            "mime_type": mime,
        }, None
    except Exception as exc:
        logger.exception("Storage upload error: %s", exc)
        return None, str(exc)

def delete_storage(path):
    if not path or not supabase_configured():
        return False
    try:
        r = requests.delete(
            sb_storage_url(path),
            headers=sb_headers(),
            timeout=20,
        )
        return r.ok
    except Exception:
        return False

# ============================================================
# DECORATORS / LOGGING
# ============================================================

def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_user():
            flash("Please log in first.", "warning")
            return redirect(url_for("login", next=request.path))
        return fn(*args, **kwargs)
    return wrapper

def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = current_user()
        if not user:
            flash("Administrator login required.", "warning")
            return redirect(url_for("login"))
        if not user.get("is_admin"):
            flash("Administrator access required.", "danger")
            return redirect(url_for("dashboard"))
        return fn(*args, **kwargs)
    return wrapper

def driver_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = current_user()
        if not user:
            flash("Driver login required.", "warning")
            return redirect(url_for("login"))
        if user.get("role") not in ("driver", "admin") and not user.get("is_admin"):
            flash("Driver account required.", "danger")
            return redirect(url_for("dashboard"))
        return fn(*args, **kwargs)
    return wrapper

def log_activity(action, description="", user_id=None):
    uid = user_id or (current_user() or {}).get("id")
    payload = {"action": action, "description": description}
    if uid:
        payload["user_id"] = uid
    try:
        db_insert("activity_logs", payload)
    except Exception:
        pass

# ============================================================
# GEOLOCATION
# ============================================================

def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0088
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = (
        math.sin(dp / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    )
    return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

def safe_float(value):
    try:
        return float(value)
    except Exception:
        return None

def latest_driver_locations():
    rows = db_select(
        "driver_locations",
        order="created_at.desc",
        limit=1000
    )
    latest = {}
    for row in rows:
        uid = row.get("driver_id") or row.get("user_id")
        if uid and uid not in latest:
            latest[str(uid)] = row
    return latest

def provider_profile(provider_id):
    for table in ("driver_profiles", "doctor_profiles", "teacher_profiles", "profiles"):
        row = first_row(table, {"provider_id": provider_id})
        if row:
            return row
    return None

# ============================================================
# TEMPLATE
# ============================================================

BASE_HTML = r""" <!doctype html> <html lang="en"> <head> <meta charset="utf-8"> <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1"> <meta name="description" content="KOJA AFRICA — academic questions, assignments, documents, professional services and live delivery services in Africa."> <meta name="robots" content="{% if request.path.startswith('/admin') or request.path.startswith('/api/') or request.path in ['/login','/register','/dashboard'] %}noindex,nofollow{% else %}index,follow,max-image-preview:large{% endif %}"> <meta name="googlebot" content="{% if request.path.startswith('/admin') or request.path.startswith('/api/') or request.path in ['/login','/register','/dashboard'] %}noindex,nofollow{% else %}index,follow{% endif %}"> <meta name="google-site-verification" content="u4nfIf5MfXm0iVvECSQeYAov4Tz4601ayY5kYzNc4ko"> <link rel="canonical" href="{{ SITE_URL }}{{ request.path }}"> <meta property="og:type" content="website"> <meta property="og:site_name" content="KOJA AFRICA"> <meta property="og:title" content="{{ title or 'KOJA AFRICA' }}"> <meta property="og:description" content="Academic questions, assignments, documents, professional services and live delivery services."> <meta property="og:url" content="{{ SITE_URL }}{{ request.path }}"> <title>{{ title or "KOJA AFRICA" }}</title> <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.css"> <style> *{box-sizing:border-box} body{margin:0;font-family:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#f5f7fb;color:#172033} nav{background:#10233f;color:#fff;padding:12px 15px;position:sticky;top:0;z-index:1000} .nav-inner{max-width:1250px;margin:auto;display:flex;align-items:center;gap:7px;flex-wrap:wrap} .brand{font-weight:800;font-size:19px;margin-right:auto} nav a{color:#fff;text-decoration:none;padding:8px 9px;border-radius:7px} nav a:hover{background:rgba(255,255,255,.12)} .container{width:min(1250px,calc(100% - 24px));margin:20px auto 50px} .card{background:#fff;border-radius:13px;padding:18px;margin-bottom:16px;box-shadow:0 3px 14px rgba(0,0,0,.06)} .hero{background:linear-gradient(135deg,#10233f,#176b87);color:#fff;padding:28px 20px;border-radius:15px;margin-bottom:18px} h1,h2,h3{margin-top:0} .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:15px} input,select,textarea,button{width:100%;padding:11px 12px;margin-top:6px;margin-bottom:12px;border-radius:8px;border:1px solid #ccd3df;font:inherit} textarea{min-height:120px} button,.btn{display:inline-block;background:#176b87;color:#fff;border:0;text-decoration:none;cursor:pointer;padding:10px 14px;border-radius:8px} .btn.secondary{background:#5f6b7a}.btn.success{background:#177245}.btn.danger{background:#a62d2d}.btn.warning{background:#9b6b00} table{width:100%;border-collapse:collapse} th,td{border-bottom:1px solid #e4e7ec;padding:9px;text-align:left;vertical-align:top} .alert{padding:12px;border-radius:8px;margin-bottom:10px;background:#eaf2ff} .stat{padding:18px;background:#fff;border-radius:12px;box-shadow:0 2px 10px rgba(0,0,0,.05)} .big{font-size:28px;font-weight:800} .small{color:#667085;font-size:13px}.badge{display:inline-block;padding:4px 8px;border-radius:20px;background:#e7eef5;font-size:12px} #map{height:430px;border-radius:12px;overflow:hidden} .map-small{height:300px!important} .driver-card{border:2px solid #e4e7ec} .driver-card.selected{border-color:#176b87} .online{color:#177245;font-weight:700} .offline{color:#a62d2d;font-weight:700} footer{text-align:center;color:#667085;padding:30px} .actions{display:flex;gap:8px;flex-wrap:wrap}.actions .btn,.actions button{width:auto} @media(max-width:650px){nav a{font-size:12px}.container{width:min(100% - 14px,1250px)}table{display:block;overflow-x:auto}#map{height:350px}.actions .btn,.actions button{width:100%}} </style> </head> <body> <nav> <div class="nav-inner"> <div class="brand">KOJA AFRICA</div> <a href="{{ url_for('home') }}">Home</a> {% if user %} <a href="{{ url_for('dashboard') }}">Dashboard</a> <a href="{{ url_for('services') }}">Services</a> <a href="{{ url_for('questions') }}">Questions</a> <a href="{{ url_for('assignments') }}">Assignments</a> <a href="{{ url_for('universities') }}">Universities</a> <a href="{{ url_for('deliveries') }}">Deliveries</a> <a href="{{ url_for('drivers') }}">Drivers</a> {% if user.role in ['driver','admin'] or user.is_admin %} <a href="{{ url_for('driver_dashboard') }}">Driver</a> {% endif %} <a href="{{ url_for('logout') }}">Logout</a> {% else %} <a href="{{ url_for('login') }}">Login</a> <a href="{{ url_for('register') }}">Register</a> {% endif %} {% if user and user.is_admin %}<a href="{{ url_for('admin') }}">Admin</a>{% endif %} </div> </nav> <div class="container"> {% with messages=get_flashed_messages(with_categories=true) %} {% for category,message in messages %}<div class="alert">{{ message }}</div>{% endfor %} {% endwith %} {{ body|safe }} </div> <footer>KOJA AFRICA — Knowledge • Questions • Answers<br>Academic • Professional • Agricultural • Health • Transport Services</footer> <script src="https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.js"></script> </body> </html> """

def render_page(title, body_template, **context):
    context["user"] = current_user()
    body = render_template_string(body_template, **context)
    return render_template_string(
        BASE_HTML,
        title=title,
        body=body,
        user=current_user()
    )

# ============================================================
# HOME / HEALTH
# ============================================================

@app.route("/")
def home():
    return render_page("KOJA AFRICA", r""" <div class="hero"> <h1>KOJA AFRICA</h1> <p>Knowledge • Questions • Answers</p> <p>Academic services, university applications, CV creation, farmer registration, professional bookings and delivery services.</p> {% if not user %} <div class="actions"> <a class="btn" href="{{ url_for('register') }}">Create Account</a> <a class="btn secondary" href="{{ url_for('login') }}">Login</a> </div> {% endif %} </div> <div class="grid"> <div class="card"><h3>Academic</h3><p>Questions, assignments and learning resources.</p><a class="btn" href="{{ url_for('questions') }}">Questions</a></div> <div class="card"><h3>University</h3><p>Choose a university, programme and academic year.</p><a class="btn" href="{{ url_for('universities') }}">Universities</a></div> <div class="card"><h3>CV</h3><p>Create a professional CV.</p><a class="btn" href="{{ url_for('cv') }}">Create CV</a></div> <div class="card"><h3>Farmers</h3><p>Submit agricultural registration information.</p><a class="btn" href="{{ url_for('farmer') }}">Farmer Portal</a></div> <div class="card"><h3>Doctors</h3><p>Find a doctor and request an appointment.</p><a class="btn" href="{{ url_for('doctors') }}">Doctors</a></div> <div class="card"><h3>Teachers</h3><p>Find teachers/tutors by subject and grade.</p><a class="btn" href="{{ url_for('teachers') }}">Teachers</a></div> <div class="card"><h3>Deliveries</h3><p>Find nearby drivers and send delivery requests.</p><a class="btn" href="{{ url_for('deliveries') }}">Delivery</a></div> <div class="card"><h3>Live GPS</h3><p>Drivers can share their live location.</p><a class="btn" href="{{ url_for('tracking') }}">Driver GPS</a></div> </div> """)

@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "application": APP_NAME,
        "supabase_configured": supabase_configured(),
        "gps_table_available": table_exists("driver_locations"),
        "timestamp": utc_now(),
        "python": os.sys.version.split()[0],
    })

# ============================================================
# REGISTER / LOGIN
# ============================================================

@app.route("/register", methods=["GET","POST"])
def register():
    if request.method == "POST":
        full_name = clean(request.form.get("full_name"))
        email = clean(request.form.get("email")).lower()
        phone = clean(request.form.get("phone"))
        password = request.form.get("password","")
        role = clean(request.form.get("role")) or "student"

        if role not in ("student","driver","teacher","doctor"):
            role = "student"

        if not full_name or not email or not password:
            flash("Full name, email and password are required.","danger")
            return redirect(url_for("register"))
        if len(password) < 6:
            flash("Password must contain at least 6 characters.","danger")
            return redirect(url_for("register"))
        if find_user_by_email(email):
            flash("An account with this email already exists. Please log in.","warning")
            return redirect(url_for("login"))

        user_id = str(uuid.uuid4())
        payload = {
            "id": user_id,
            "name": full_name,
            "full_name": full_name,
            "email": email,
            "phone": phone or None,
            "password_hash": generate_password_hash(password),
            "role": role,
            "is_admin": False,
            "is_active": True,
            "created_at": utc_now(),
        }

        row, error = db_insert("profiles", payload)
        if error:
            old = {
                "id": user_id,
                "full_name": full_name,
                "email": email,
                "phone": phone or None,
                "password_hash": payload["password_hash"],
            }
            row, error = db_insert("KOJA ZM", old)

        if error:
            flash("Registration failed. Check Render logs for the exact Supabase column error.","danger")
            return redirect(url_for("register"))

        login_user(row or payload)
        log_activity("registration","New KOJA account registered.")
        flash("Account created successfully.","success")
        return redirect(url_for("dashboard"))

    return render_page("Register", r""" <div class="card" style="max-width:600px;margin:auto"> <h2>Create KOJA Account</h2> <form method="post"> <label>Full Name</label><input name="full_name" required> <label>Email</label><input name="email" type="email" required> <label>Phone</label><input name="phone"> <label>Account Type</label> <select name="role"> <option value="student">Student / Customer</option> <option value="driver">Delivery Driver</option> <option value="teacher">Teacher / Tutor</option> <option value="doctor">Doctor</option> </select> <label>Password</label><input name="password" type="password" minlength="6" required> <button type="submit">Create Account</button> </form> <p>Already registered? <a href="{{ url_for('login') }}">Login</a></p> </div> """)

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        email = clean(request.form.get("email")).lower()
        password = request.form.get("password","")
        user = find_user_by_email(email)

        # First: existing KOJA profile password.
        if user and password_matches(user,password):
            if user.get("is_active") is False:
                flash("This account is inactive.","danger")
                return redirect(url_for("login"))
            login_user(user)
            log_activity("login","User logged into KOJA.")
            return redirect(request.args.get("next") if request.args.get("next","").startswith("/") else url_for("dashboard"))

        # Second: Supabase Auth compatibility.
        auth = supabase_auth_login(email,password)
        if auth and auth.get("user"):
            au = auth["user"]
            profile = find_user_by_id(au.get("id"))
            if not profile:
                profile, _ = create_local_profile(
                    au.get("id"), au.get("email") or email,
                    au.get("user_metadata",{}).get("full_name","")
                )
            login_user(profile, auth)
            log_activity("login","User logged in through Supabase Auth.")
            return redirect(request.args.get("next") if request.args.get("next","").startswith("/") else url_for("dashboard"))

        flash("Invalid login credentials. Use the same email and password used to create the KOJA account.","danger")
        return redirect(url_for("login"))

    return render_page("Login", r""" <div class="card" style="max-width:500px;margin:auto"> <h2>KOJA Login</h2> <p class="small">KOJA supports its local profile password and, when configured, Supabase Auth accounts.</p> <form method="post"> <label>Email</label><input name="email" type="email" autocomplete="email" required> <label>Password</label><input name="password" type="password" autocomplete="current-password" required> <button type="submit">Login</button> </form> <p>No account? <a href="{{ url_for('register') }}">Create one</a></p> </div> """)

@app.route("/logout")
def logout():
    if current_user():
        log_activity("logout","User logged out.")
    session.clear()
    flash("You have been logged out.","success")
    return redirect(url_for("home"))

# ============================================================
# DASHBOARD / SERVICES
# ============================================================

@app.route("/dashboard")
@login_required
def dashboard():
    user = current_user()
    questions_count = len(db_select("questions",filters={"user_id":user["id"]},limit=1000))
    deliveries_count = len(db_select("deliveries",filters={"customer_id":user["id"]},limit=1000))
    appointments_count = len(db_select("appointments",filters={"client_id":user["id"]},limit=1000))
    return render_page("Dashboard", r""" <div class="hero"><h2>Welcome, {{ user.name }}</h2><p>{{ user.email }}</p></div> <div class="grid"> <div class="stat"><div class="big">{{ questions_count }}</div>Academic Questions</div> <div class="stat"><div class="big">{{ deliveries_count }}</div>Deliveries</div> <div class="stat"><div class="big">{{ appointments_count }}</div>Appointments</div> <div class="stat"><div class="big">{{ "ADMIN" if user.is_admin else user.role|upper }}</div>Account</div> </div> <div class="card"><h3>KOJA Services</h3> <div class="grid"> <a class="btn" href="{{ url_for('cv') }}">Create CV</a> <a class="btn" href="{{ url_for('universities') }}">University Application</a> <a class="btn" href="{{ url_for('farmer') }}">Farmer Registration</a> <a class="btn" href="{{ url_for('doctors') }}">Doctor Booking</a> <a class="btn" href="{{ url_for('teachers') }}">Teacher Booking</a> <a class="btn" href="{{ url_for('deliveries') }}">Find Driver / Delivery</a> {% if user.role in ['driver','admin'] or user.is_admin %}<a class="btn" href="{{ url_for('driver_dashboard') }}">Driver Dashboard</a>{% endif %} </div></div> """,questions_count=questions_count,deliveries_count=deliveries_count,appointments_count=appointments_count)

@app.route("/services")
@login_required
def services():
    return render_page("Services", r""" <div class="hero"><h2>KOJA Services</h2><p>Choose a service.</p></div> <div class="grid"> <div class="card"><h3>Academic Questions</h3><a class="btn" href="{{ url_for('questions') }}">Open</a></div> <div class="card"><h3>Assignments</h3><a class="btn" href="{{ url_for('assignments') }}">Open</a></div> <div class="card"><h3>CV</h3><a class="btn" href="{{ url_for('cv') }}">Open</a></div> <div class="card"><h3>University Applications</h3><a class="btn" href="{{ url_for('universities') }}">Open</a></div> <div class="card"><h3>Farmer Registration</h3><a class="btn" href="{{ url_for('farmer') }}">Open</a></div> <div class="card"><h3>Doctors</h3><a class="btn" href="{{ url_for('doctors') }}">Open</a></div> <div class="card"><h3>Teachers</h3><a class="btn" href="{{ url_for('teachers') }}">Open</a></div> <div class="card"><h3>Deliveries</h3><a class="btn" href="{{ url_for('deliveries') }}">Open</a></div> </div> """)

# ============================================================
# QUESTIONS / ASSIGNMENTS
# ============================================================

@app.route("/questions", methods=["GET","POST"])
@login_required
def questions():
    user = current_user()
    if request.method == "POST":
        question_text = clean(request.form.get("question"))
        subject = clean(request.form.get("subject"))
        if not question_text:
            flash("Enter your question.","danger")
            return redirect(url_for("questions"))

        payload = {
            "id":str(uuid.uuid4()),"user_id":user["id"],
            "question":question_text,"subject":subject or None,
            "status":"submitted","created_at":utc_now()
        }
        row,error = db_insert("questions",payload)
        if error:
            row,error = db_insert("questions",{
                "id":str(uuid.uuid4()),"user_id":user["id"],
                "question":question_text
            })
        if error:
            flash("Question could not be submitted. Check your questions table columns.","danger")
        else:
            flash("Question submitted.","success")
            log_activity("question_created","Student submitted an academic question.")
        return redirect(url_for("questions"))

    rows = db_select("questions",filters={"user_id":user["id"]},order="created_at.desc",limit=100)
    return render_page("Questions",r""" <div class="card"><h2>Ask an Academic Question</h2> <form method="post"> <label>Subject</label><input name="subject" placeholder="Mathematics, Biology, Chemistry..."> <label>Question</label><textarea name="question" required></textarea> <button type="submit">Submit Question</button> </form></div> <div class="card"><h2>My Questions</h2> {% for q in rows %} <div class="card"><strong>{{ q.get("subject") or "Academic" }}</strong> <p>{{ q.get("question") or q.get("question_text") }}</p> {% if q.get("answer") %}<hr><strong>Answer</strong><p>{{ q.get("answer") }}</p>{% endif %} <span class="badge">{{ q.get("status") or "Submitted" }}</span></div> {% else %}<p>No questions submitted yet.</p>{% endfor %} </div> """,rows=rows)

@app.route("/assignments", methods=["GET","POST"])
@login_required
def assignments():
    user=current_user()
    if request.method=="POST":
        title=clean(request.form.get("title"))
        description=clean(request.form.get("description"))
        file=request.files.get("file")
        uploaded=None
        if file and file.filename:
            uploaded,error=upload_storage(file,"assignments")
            if error:
                flash(f"Upload failed: {error}","danger")
                return redirect(url_for("assignments"))

        payload={
            "id":str(uuid.uuid4()),
            "student_id":user["id"],"user_id":user["id"],
            "title":title,"description":description,
            "status":"submitted","created_at":utc_now()
        }
        if uploaded:
            payload.update({
                "file_name":uploaded["file_name"],
                "file_path":uploaded["path"],
                "file_url":uploaded["url"],
                "file_size":uploaded["file_size"],
                "mime_type":uploaded["mime_type"]
            })
        row,error=db_insert("assignments",payload)
        if error:
            minimal={"id":str(uuid.uuid4()),"title":title,"description":description}
            if uploaded:
                minimal.update({"file_name":uploaded["file_name"],"file_path":uploaded["path"],"file_url":uploaded["url"]})
            row,error=db_insert("assignments",minimal)
        if error:
            flash("Assignment could not be saved. Check assignments table columns.","danger")
        else:
            flash("Assignment uploaded successfully.","success")
        return redirect(url_for("assignments"))

    rows=db_select("assignments",order="created_at.desc",limit=100)
    return render_page("Assignments",r""" <div class="card"><h2>Upload Assignment</h2> <form method="post" enctype="multipart/form-data"> <label>Assignment Title</label><input name="title" required> <label>Description / Question</label><textarea name="description"></textarea> <label>Assignment File</label><input type="file" name="file" accept=".pdf,.doc,.docx,.txt,.jpg,.jpeg,.png"> <button type="submit">Upload Assignment</button> </form></div> <div class="card"><h2>Assignments</h2> {% for item in rows %} <div class="card"><h3>{{ item.get("title") or "Assignment" }}</h3> <p>{{ item.get("description") or "" }}</p> {% if item.get("file_url") %}<a class="btn" href="{{ item.get('file_url') }}" target="_blank">Download File</a>{% endif %} {% if item.get("answer_file_url") %}<a class="btn success" href="{{ item.get('answer_file_url') }}" target="_blank">Download Answer</a>{% endif %} {% if item.get("answered_file_url") %}<a class="btn success" href="{{ item.get('answered_file_url') }}" target="_blank">Download Answered File</a>{% endif %} </div> {% else %}<p>No assignments found.</p>{% endfor %} </div> """,rows=rows)

# ============================================================
# CV
# ============================================================

@app.route("/cv",methods=["GET","POST"])
@login_required
def cv():
    user=current_user()
    if request.method=="POST":
        data={
            "full_name":clean(request.form.get("full_name")),
            "phone":clean(request.form.get("phone")),
            "email":clean(request.form.get("email")),
            "address":clean(request.form.get("address")),
            "profile":clean(request.form.get("profile")),
            "education":clean(request.form.get("education")),
            "experience":clean(request.form.get("experience")),
            "skills":clean(request.form.get("skills")),
            "references":clean(request.form.get("references")),
        }
        return render_page("CV Preview",r""" <div class="card"> <h1>{{ data.full_name }}</h1><p>{{ data.phone }} | {{ data.email }} | {{ data.address }}</p> {% if data.profile %}<h2>Professional Profile</h2><p>{{ data.profile }}</p>{% endif %} {% if data.education %}<h2>Education</h2><p style="white-space:pre-wrap">{{ data.education }}</p>{% endif %} {% if data.experience %}<h2>Work Experience</h2><p style="white-space:pre-wrap">{{ data.experience }}</p>{% endif %} {% if data.skills %}<h2>Skills</h2><p style="white-space:pre-wrap">{{ data.skills }}</p>{% endif %} {% if data.references %}<h2>References</h2><p style="white-space:pre-wrap">{{ data.references }}</p>{% endif %} <hr><button onclick="window.print()">Print / Save as PDF</button> </div> """,data=data)

    return render_page("CV Builder",r""" <div class="card"><h2>CV Builder</h2> <form method="post"> <label>Full Name</label><input name="full_name" value="{{ user.name }}" required> <label>Phone</label><input name="phone" value="{{ user.phone or '' }}"> <label>Email</label><input name="email" value="{{ user.email or '' }}" required> <label>Address</label><input name="address"> <label>Professional Profile</label><textarea name="profile"></textarea> <label>Education</label><textarea name="education"></textarea> <label>Work Experience</label><textarea name="experience"></textarea> <label>Skills</label><textarea name="skills"></textarea> <label>References</label><textarea name="references"></textarea> <button type="submit">Generate CV</button> </form> <p class="small">Use Print / Save as PDF in the Android browser. No ReportLab package is required.</p> </div> """)

# ============================================================
# FARMER
# ============================================================

@app.route("/farmer",methods=["GET","POST"])
@login_required
def farmer():
    user=current_user()
    if request.method=="POST":
        data={
            "id":str(uuid.uuid4()),"user_id":user["id"],
            "nrc":clean(request.form.get("nrc")),
            "date_of_birth":request.form.get("date_of_birth") or None,
            "first_name":clean(request.form.get("first_name")),
            "middle_names":clean(request.form.get("middle_names")),
            "last_name":clean(request.form.get("last_name")),
            "gender":clean(request.form.get("gender")),
            "phone":clean(request.form.get("phone")),
            "location":clean(request.form.get("location")),
            "payment_method":clean(request.form.get("payment_method")),
            "provider":clean(request.form.get("provider")),
            "branch":clean(request.form.get("branch")),
            "account_number":clean(request.form.get("account_number")),
            "account_name":clean(request.form.get("account_name")),
            "status":"submitted","created_at":utc_now()
        }
        f=request.files.get("nrc_document")
        if f and f.filename:
            uploaded,error=upload_storage(f,"farmer-nrc")
            if error:
                flash(error,"danger"); return redirect(url_for("farmer"))
            data["nrc_document_url"]=uploaded["url"]
            data["nrc_document_path"]=uploaded["path"]

        row,error=db_insert("farmer_registrations",data)
        if error:
            minimal={k:data[k] for k in ("id","user_id","nrc","first_name","middle_names","last_name","gender","phone","location")}
            row,error=db_insert("farmer_registrations",minimal)
        if error:
            flash("Farmer registration could not be submitted. Check the farmer_registrations columns.","danger")
        else:
            flash("Farmer registration submitted successfully.","success")
            log_activity("farmer_registration","Farmer registration submitted.")
        return redirect(url_for("farmer"))

    return render_page("Farmer Registration",r""" <div class="hero"><h2>KOJA Farmer Registration</h2><p>Register your agricultural service request.</p></div> <div class="card"><form method="post" enctype="multipart/form-data"> <h3>Personal Details</h3> <label>NRC</label><input name="nrc" required> <label>Date of Birth</label><input name="date_of_birth" type="date"> <label>First Name</label><input name="first_name" required> <label>Middle Names</label><input name="middle_names"> <label>Last Name</label><input name="last_name" required> <label>Gender</label><select name="gender"><option value="">Select</option><option>Male</option><option>Female</option></select> <label>Phone</label><input name="phone" required> <label>NRC Card</label><input type="file" name="nrc_document" accept=".jpg,.jpeg,.png,.pdf"> <h3>Farming Location</h3><label>Location</label><input name="location" placeholder="Province / District / Chiefdom / Camp"> <h3>Payment Details</h3> <label>Payment Method</label><select name="payment_method"><option>Bank Account</option><option>Mobile Money (MNO)</option><option>Wallet</option></select> <label>Provider</label><input name="provider" placeholder="Bank or mobile-money provider"> <label>Branch</label><input name="branch"> <label>Account / Mobile Number</label><input name="account_number"> <label>Account Name</label><input name="account_name"> <button type="submit">Submit Farmer Registration</button> </form></div> """)

# ============================================================
# DOCTORS / TEACHERS
# ============================================================

@app.route("/doctors")
@login_required
def doctors():
    doctors=db_select("doctor_profiles",order="created_at.desc",limit=100)
    return render_page("Doctors",r""" <div class="hero"><h2>Find a Doctor</h2><p>Choose a specific doctor and request an appointment.</p></div> <div class="grid"> {% for d in doctors %} <div class="card"> <h3>{{ d.get("full_name") or d.get("doctor_name") or "Doctor" }}</h3> <p><strong>Specialty:</strong> {{ d.get("specialty") or "General" }}</p> <p><strong>Hospital/Clinic:</strong> {{ d.get("hospital_clinic") or "Not specified" }}</p> {% if d.get("consultation_fee") %}<p><strong>Fee:</strong> {{ d.get("currency") or "ZMW" }} {{ d.get("consultation_fee") }}</p>{% endif %} <div class="actions"> <a class="btn" href="{{ url_for('book_doctor',provider_id=d.get('provider_id')) }}">Book This Doctor</a> <a class="btn secondary" href="{{ url_for('provider_map',provider_id=d.get('provider_id'),provider_type='doctor') }}">View Location</a> </div></div> {% else %}<div class="card"><p>No doctor profiles have been registered yet.</p></div>{% endfor %} </div> """,doctors=doctors)

@app.route("/doctor/book/<provider_id>",methods=["GET","POST"])
@login_required
def book_doctor(provider_id):
    user=current_user()
    doctor=first_row("doctor_profiles",{"provider_id":provider_id})
    if not doctor: abort(404)
    if request.method=="POST":
        payload={
            "id":str(uuid.uuid4()),"client_id":user["id"],"provider_id":provider_id,
            "appointment_type":"doctor","appointment_date":request.form.get("appointment_date"),
            "start_time":request.form.get("start_time"),"end_time":request.form.get("end_time"),
            "location":clean(request.form.get("location")),"status":"requested",
            "notes":clean(request.form.get("notes")),"created_at":utc_now(),"updated_at":utc_now()
        }
        row,error=db_insert("appointments",payload)
        if error: flash("Appointment could not be created: "+str(error)[:500],"danger")
        else: flash("Doctor booking request submitted.","success")
        return redirect(url_for("dashboard"))
    return render_page("Book Doctor",r""" <div class="card"><h2>Book {{ doctor.get("full_name") or doctor.get("doctor_name") or "Doctor" }}</h2> <p><strong>Specialty:</strong> {{ doctor.get("specialty") or "General" }}</p> <form method="post"> <label>Date</label><input type="date" name="appointment_date" required> <label>Start Time</label><input type="time" name="start_time" required> <label>End Time</label><input type="time" name="end_time"> <label>Location</label><input name="location" placeholder="Hospital, clinic or online"> <label>Notes</label><textarea name="notes"></textarea> <button type="submit">Request Appointment</button> </form></div> """,doctor=doctor)

@app.route("/teachers")
@login_required
def teachers():
    teachers=db_select("teacher_profiles",order="created_at.desc",limit=100)
    return render_page("Teachers",r""" <div class="hero"><h2>Find a Teacher / Tutor</h2><p>Choose a specific teacher for tutoring.</p></div> <div class="grid"> {% for t in teachers %} <div class="card"> <h3>{{ t.get("full_name") or t.get("teacher_name") or "Teacher" }}</h3> <p><strong>Subjects:</strong> {{ t.get("subjects") or "Not specified" }}</p> <p><strong>Grades:</strong> {{ t.get("grade_levels") or "Not specified" }}</p> <p><strong>Qualification:</strong> {{ t.get("qualification") or "Not specified" }}</p> {% if t.get("hourly_rate") %}<p><strong>Rate:</strong> {{ t.get("currency") or "ZMW" }} {{ t.get("hourly_rate") }}/hour</p>{% endif %} <a class="btn" href="{{ url_for('book_teacher',provider_id=t.get('provider_id')) }}">Book Teacher</a> <a class="btn secondary" href="{{ url_for('provider_map',provider_id=t.get('provider_id'),provider_type='teacher') }}">View Location</a> </div> {% else %}<div class="card"><p>No teacher profiles have been registered yet.</p></div>{% endfor %} </div> """,teachers=teachers)

@app.route("/teacher/book/<provider_id>",methods=["GET","POST"])
@login_required
def book_teacher(provider_id):
    user=current_user()
    teacher=first_row("teacher_profiles",{"provider_id":provider_id})
    if not teacher: abort(404)
    if request.method=="POST":
        payload={
            "id":str(uuid.uuid4()),"client_id":user["id"],"provider_id":provider_id,
            "appointment_type":"teacher","appointment_date":request.form.get("appointment_date"),
            "start_time":request.form.get("start_time"),"end_time":request.form.get("end_time"),
            "location":clean(request.form.get("location")),"status":"requested",
            "notes":clean(request.form.get("notes")),"created_at":utc_now(),"updated_at":utc_now()
        }
        row,error=db_insert("appointments",payload)
        if error: flash("Teacher booking failed: "+str(error)[:500],"danger")
        else: flash("Teacher booking request submitted.","success")
        return redirect(url_for("dashboard"))
    return render_page("Book Teacher",r""" <div class="card"><h2>Book {{ teacher.get("full_name") or teacher.get("teacher_name") or "Teacher" }}</h2> <p>{{ teacher.get("subjects") or "" }}</p> <form method="post"> <label>Date</label><input type="date" name="appointment_date" required> <label>Start Time</label><input type="time" name="start_time" required> <label>End Time</label><input type="time" name="end_time"> <label>Location / Online</label><input name="location"> <label>Notes</label><textarea name="notes"></textarea> <button type="submit">Book Teacher</button> </form></div> """,teacher=teacher)

# ============================================================
# DRIVER REGISTRATION / PROFILE
# ============================================================

DRIVER_PROFILE_COLUMNS = (
    "id,provider_id,vehicle_type,vehicle_make,vehicle_model,"
    "vehicle_registration,driving_license_number,service_area,"
    "verification_status,created_at"
)


def get_driver_provider(user_id):
    """Return the service_providers row belonging to the logged-in profile."""
    if not user_id:
        return None
    return first_row("service_providers", {"user_id": user_id, "provider_type": "driver"})


def ensure_driver_provider(user):
    """Create the provider record first; driver_profiles.provider_id points to it."""
    provider = get_driver_provider(user.get("id"))
    if provider:
        return provider, None

    payload = {
        "id": str(uuid.uuid4()),
        "user_id": user.get("id"),
        "provider_type": "driver",
        "full_name": user.get("name") or user.get("full_name") or "Driver",
        "phone": user.get("phone") or None,
        "email": user.get("email") or None,
        "verification_status": "pending",
        "is_available": False,
        "is_active": True,
    }
    provider, error = db_insert("service_providers", payload)
    if error:
        return None, error
    return provider or payload, None


@app.route("/driver/register", methods=["GET", "POST"])
@app.route("/drivers/register", methods=["GET", "POST"])
@login_required
def driver_register():
    user = current_user() or {}
    provider = get_driver_provider(user.get("id"))
    existing = None
    if provider:
        existing = first_row("driver_profiles", {"provider_id": provider.get("id")})

    if request.method == "POST":
        vehicle_type = clean(request.form.get("vehicle_type"))
        vehicle_make = clean(request.form.get("vehicle_make"))
        vehicle_model = clean(request.form.get("vehicle_model"))
        vehicle_registration = clean(request.form.get("vehicle_registration"))
        driving_license_number = clean(request.form.get("driving_license_number"))
        service_area = clean(request.form.get("service_area"))

        if not vehicle_type or not vehicle_registration or not driving_license_number:
            flash("Vehicle type, vehicle registration and driving licence number are required.", "danger")
            return redirect(url_for("driver_register"))

        provider, provider_error = ensure_driver_provider(user)
        if provider_error or not provider or not provider.get("id"):
            logger.error("Driver provider creation failed: %s", provider_error)
            flash("Driver registration failed while creating the service provider record. " + str(provider_error or "Unknown database error")[:700], "danger")
            return redirect(url_for("driver_register"))

        provider_id = str(provider["id"])
        existing = first_row("driver_profiles", {"provider_id": provider_id})

        # IMPORTANT: these are the exact confirmed driver_profiles columns.
        payload = {
            "provider_id": provider_id,
            "vehicle_type": vehicle_type,
            "vehicle_make": vehicle_make or None,
            "vehicle_model": vehicle_model or None,
            "vehicle_registration": vehicle_registration,
            "driving_license_number": driving_license_number,
            "service_area": service_area or None,
            "verification_status": "pending",
        }

        if existing and existing.get("id"):
            row, error = db_update("driver_profiles", {"id": existing["id"]}, payload)
        else:
            payload["id"] = str(uuid.uuid4())
            row, error = db_insert("driver_profiles", payload)

        if error:
            logger.error("Exact driver_profiles insert/update failed: %s", error)
            flash("Driver registration failed: " + str(error)[:900], "danger")
            return redirect(url_for("driver_register"))

        # A successful driver profile makes the account a driver, but verification
        # remains pending until an administrator approves the profile.
        db_update("profiles", {"id": user["id"]}, {"role": "driver"})
        session["user"]["role"] = "driver"
        session["user"]["driver_provider_id"] = provider_id
        session["user"]["vehicle_type"] = vehicle_type
        session["user"]["vehicle_registration"] = vehicle_registration
        session["user"]["driving_license_number"] = driving_license_number
        log_activity("driver_registration", "Driver profile submitted for verification.")
        flash("Driver registration submitted successfully. Your profile is pending admin verification.", "success")
        return redirect(url_for("driver_dashboard"))

    return render_page("Driver Registration", r""" <div class="hero"><h2>Driver Registration</h2> <p>Complete your driver and vehicle information. A KOJA administrator must verify your registration before customers can request you.</p></div> <div class="card"> <form method="post"> <label>Vehicle Type</label> <select name="vehicle_type" required> <option value="">Select vehicle type</option> <option>Motorcycle</option><option>Car</option><option>Van</option><option>Pickup</option><option>Truck</option><option>Bicycle</option> </select> <label>Vehicle Make</label><input name="vehicle_make" value="{{ existing.get('vehicle_make','') if existing else '' }}" placeholder="Toyota, Honda, etc."> <label>Vehicle Model</label><input name="vehicle_model" value="{{ existing.get('vehicle_model','') if existing else '' }}" placeholder="Model"> <label>Vehicle Registration</label><input name="vehicle_registration" value="{{ existing.get('vehicle_registration','') if existing else '' }}" required placeholder="ABC 1234"> <label>Driving Licence Number</label><input name="driving_license_number" value="{{ existing.get('driving_license_number','') if existing else '' }}" required> <label>Service Area</label><input name="service_area" value="{{ existing.get('service_area','') if existing else '' }}" placeholder="e.g. Kitwe CBD, Chimwemwe"> {% if existing %}<p class="small">Current verification status: <strong>{{ existing.get('verification_status') or 'pending' }}</strong></p>{% endif %} <button type="submit">Submit Driver Registration</button> </form> </div> """, existing=existing)

# ============================================================

# DRIVER DASHBOARD / ONLINE STATUS / REQUESTS
# ============================================================

@app.route("/driver")
@login_required
def driver_dashboard():
    user = current_user()
    provider = get_driver_provider(user.get("id"))
    profile = first_row("driver_profiles", {"provider_id": provider.get("id")}) if provider else None
    if not profile:
        return redirect(url_for("driver_register"))

    provider_id = str(provider.get("id"))
    locations = db_select("driver_locations", filters={"driver_id": provider_id}, order="created_at.desc", limit=1)
    latest = locations[0] if locations else None
    requests_rows = db_select("deliveries", filters={"driver_id": provider_id}, order="created_at.desc", limit=100)

    return render_page("Driver Dashboard", r""" <div class="hero"><h2>Driver Dashboard</h2> <p>{{ user.name }} — {{ profile.get('vehicle_type') or 'Vehicle' }} {{ profile.get('vehicle_registration') or '' }}</p> <p>Verification: <strong>{{ profile.get('verification_status') or 'pending' }}</strong></p></div> <div class="card"><h3>GPS / Availability</h3> <p>Current status: <span id="online-status" class="{{ 'online' if latest and latest.get('is_online') else 'offline' }}"> {{ 'ONLINE' if latest and latest.get('is_online') else 'OFFLINE' }}</span></p> <div class="actions"> <a class="btn success" href="{{ url_for('tracking') }}{% if requests_rows %}?delivery_id={{ requests_rows[0].get('id') }}{% endif %}">Open GPS & Go Online</a> <button class="btn danger" onclick="goOffline()">Go Offline</button> </div><p id="offline-status" class="small"></p></div> <div class="card"><h3>Delivery Requests / Jobs</h3> {% for d in requests_rows %}<div class="card"> <strong>{{ d.get('tracking_code') }}</strong> <p>{{ d.get('pickup_location') }} → {{ d.get('destination') }}</p> <p>Status: <span class="badge">{{ d.get('status') or 'requested' }}</span></p> <div class="actions"> {% if d.get('status') == 'requested' %} <form method="post" action="{{ url_for('driver_delivery_action',delivery_id=d.get('id'),action='accept') }}"><button class="btn success">Accept</button></form> <form method="post" action="{{ url_for('driver_delivery_action',delivery_id=d.get('id'),action='reject') }}"><button class="btn danger">Reject</button></form> {% elif d.get('status') == 'accepted' %}<form method="post" action="{{ url_for('driver_delivery_action',delivery_id=d.get('id'),action='picked_up') }}"><button class="btn">Picked Up</button></form> {% elif d.get('status') == 'picked_up' %}<form method="post" action="{{ url_for('driver_delivery_action',delivery_id=d.get('id'),action='in_transit') }}"><button class="btn">In Transit</button></form> {% elif d.get('status') == 'in_transit' %}<form method="post" action="{{ url_for('driver_delivery_action',delivery_id=d.get('id'),action='delivered') }}"><button class="btn success">Delivered</button></form>{% endif %} <a class="btn secondary" href="{{ url_for('track_delivery',tracking_code=d.get('tracking_code')) }}">Track Map</a> </div></div> {% else %}<p>No delivery requests yet.</p>{% endfor %} </div> <script> async function goOffline(){try{const r=await fetch('/api/driver/offline',{method:'POST'});const d=await r.json();document.getElementById('offline-status').textContent=d.message||'Driver is offline.';document.getElementById('online-status').textContent='OFFLINE';}catch(e){document.getElementById('offline-status').textContent='Unable to change status.'}} </script> """, profile=profile, latest=latest, requests_rows=requests_rows)

@app.route("/driver/delivery/<delivery_id>/<action>", methods=["POST"])
@driver_required
def driver_delivery_action(delivery_id, action):
    user = current_user()
    provider = get_driver_provider(user.get("id"))
    if not provider:
        flash("Driver provider record not found.", "danger")
        return redirect(url_for("driver_register"))
    provider_id = str(provider["id"])
    delivery = first_row("deliveries", {"id": delivery_id})
    if not delivery:
        abort(404)

    if action in ("accept", "reject"):
        assigned = delivery.get("driver_id")
        if assigned and str(assigned) != provider_id:
            flash("This delivery is assigned to another driver.", "danger")
            return redirect(url_for("driver_dashboard"))

    statuses = {"accept":"accepted", "reject":"rejected", "picked_up":"picked_up", "in_transit":"in_transit", "delivered":"delivered"}
    if action not in statuses:
        abort(400)
    status = statuses[action]
    payload = {"status": status, "updated_at": utc_now()}
    if action == "accept":
        payload["driver_id"] = provider_id
    row, error = db_update("deliveries", {"id": delivery_id}, payload)
    if error:
        flash("Could not update delivery status: " + str(error)[:700], "danger")
    else:
        log_activity("delivery_status", f"Delivery {delivery.get('tracking_code')} changed to {status}.")
        flash(f"Delivery status changed to {status}.", "success")
    return redirect(url_for("driver_dashboard"))

# DRIVER GPS
# ============================================================

@app.route("/tracking")
@login_required
def tracking():
    user=current_user()
    delivery_id = clean(request.args.get("delivery_id"))
    return render_page("Live GPS Tracking",r""" <div class="hero"><h2>Live Driver GPS</h2><p>Allow browser location permission. Keep this page open while driving.</p></div> <div class="card"> <label>Delivery ID (optional)</label> <input id="delivery_id" value="{{ delivery_id or '' }}" placeholder="Assigned delivery ID (automatic when opened from a job)"> <div class="actions"> <button class="btn success" onclick="startTracking()">Go Online / Start GPS</button> <button class="btn danger" onclick="stopTracking()">Stop GPS / Go Offline</button> </div> <p id="gps-status">GPS not started.</p> <div id="map"></div> </div> <script> let watchId=null,marker=null; const map=L.map("map").setView([-13.9626,28.3228],6); L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",{maxZoom:19,attribution:"&copy; OpenStreetMap contributors"}).addTo(map); function status(t){document.getElementById("gps-status").textContent=t} function startTracking(){ if(!navigator.geolocation){status("This browser does not support GPS.");return} status("Requesting GPS permission..."); watchId=navigator.geolocation.watchPosition(sendPosition,gpsError,{enableHighAccuracy:true,maximumAge:3000,timeout:15000}); } async function sendPosition(position){ const c=position.coords, lat=c.latitude, lon=c.longitude; if(!marker){marker=L.marker([lat,lon]).addTo(map).bindPopup("Your live driver location");} else marker.setLatLng([lat,lon]); map.setView([lat,lon],16); const deliveryId=document.getElementById("delivery_id").value.trim(); try{ const r=await fetch("/api/driver/location",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({ latitude:lat,longitude:lon,accuracy:c.accuracy,speed:c.speed,heading:c.heading,altitude:c.altitude,delivery_id:deliveryId||null })}); const d=await r.json(); status(d.ok?"ONLINE — GPS updated "+new Date().toLocaleTimeString():(d.message||"GPS update failed.")); }catch(e){status("Network error while sending GPS.");} } function gpsError(e){ if(e.code===1)status("Location permission denied. Allow location permission in browser settings."); else if(e.code===2)status("Device could not determine location."); else if(e.code===3)status("GPS timed out."); else status("GPS error."); } function stopTracking(){ if(watchId!==null){navigator.geolocation.clearWatch(watchId);watchId=null;} fetch("/api/driver/offline",{method:"POST",headers:{"Content-Type":"application/json"}}).then(r=>r.json()).then(d=>status(d.message||"GPS sharing stopped.")).catch(()=>status("GPS stopped locally.")); } </script> """)

@app.route("/api/driver/location", methods=["POST"])
@driver_required
def driver_location_update():
    if not table_exists("driver_locations"):
        return jsonify({"ok":False,"message":"driver_locations table is not available."}),503
    user = current_user()
    provider = get_driver_provider(user.get("id"))
    if not provider:
        return jsonify({"ok":False,"message":"Driver provider profile not found."}),404
    provider_id = str(provider["id"])
    body = request.get_json(silent=True) or {}
    lat = safe_float(body.get("latitude")); lon = safe_float(body.get("longitude"))
    if lat is None or lon is None or not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
        return jsonify({"ok":False,"message":"Invalid latitude or longitude."}),400
    payload = {
        "id": str(uuid.uuid4()), "driver_id": provider_id,
        "latitude": lat, "longitude": lon,
        "accuracy": safe_float(body.get("accuracy")),
        "speed": safe_float(body.get("speed")),
        "heading": safe_float(body.get("heading")),
        "is_online": True, "created_at": utc_now()
    }
    row, error = db_insert("driver_locations", payload)
    if error:
        logger.error("driver_locations insert failed: %s", error)
        return jsonify({"ok":False,"message":"GPS location could not be saved.","error":str(error)[:700]}),500
    delivery_id = clean(body.get("delivery_id"))
    if delivery_id:
        delivery = first_row("deliveries", {"id": delivery_id})
        if delivery and str(delivery.get("driver_id") or "") in ("", provider_id):
            db_update("deliveries", {"id":delivery_id}, {"driver_id":provider_id,"updated_at":utc_now()})
    return jsonify({"ok":True,"latitude":lat,"longitude":lon,"created_at":utc_now()})

@app.route("/api/driver/offline", methods=["POST"])
@driver_required
def driver_offline():
    user = current_user()
    provider = get_driver_provider(user.get("id"))
    if not provider:
        return jsonify({"ok":False,"message":"Driver provider profile not found."}),404
    provider_id = str(provider["id"])
    latest = first_row("driver_locations", {"driver_id":provider_id})
    payload = {
        "id":str(uuid.uuid4()), "driver_id":provider_id,
        "latitude": latest.get("latitude") if latest else None,
        "longitude": latest.get("longitude") if latest else None,
        "accuracy": latest.get("accuracy") if latest else None,
        "speed": None, "heading": None, "is_online":False,
        "created_at":utc_now()
    }
    row,error=db_insert("driver_locations",payload)
    if error:
        return jsonify({"ok":False,"message":"Could not mark driver offline.","error":str(error)[:700]}),500
    return jsonify({"ok":True,"message":"Driver is now offline."})

# ============================================================
# NEARBY DRIVERS
# ============================================================


# ============================================================

@app.route("/drivers")
@login_required
def drivers():
    return render_page("Nearby Drivers",r""" <div class="hero"><h2>Nearby Delivery Drivers</h2><p>Share your pickup/shop location and KOJA will calculate distances to online drivers.</p></div> <div class="card"> <div class="grid"> <div><label>Your Latitude</label><input id="lat" type="number" step="any" placeholder="-13.96"></div> <div><label>Your Longitude</label><input id="lon" type="number" step="any" placeholder="28.32"></div> </div> <div class="actions"> <button class="btn" onclick="locateMe()">Use My Current Location</button> <button class="btn success" onclick="findDrivers()">Find Nearby Drivers</button> </div> <p id="status" class="small"></p> </div> <div class="card"><div id="map"></div></div> <div class="card"><h3>Available Drivers</h3><div id="driver-list">Enter your location and search.</div></div> <script> let map=L.map("map").setView([-13.9626,28.3228],6),me=null,markers=[]; L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",{maxZoom:19,attribution:"&copy; OpenStreetMap contributors"}).addTo(map); function locateMe(){ if(!navigator.geolocation){document.getElementById("status").textContent="GPS is not supported.";return} document.getElementById("status").textContent="Requesting your location..."; navigator.geolocation.getCurrentPosition(p=>{ document.getElementById("lat").value=p.coords.latitude; document.getElementById("lon").value=p.coords.longitude; if(me)me.setLatLng([p.coords.latitude,p.coords.longitude]);else me=L.marker([p.coords.latitude,p.coords.longitude]).addTo(map).bindPopup("Your pickup/shop location"); map.setView([p.coords.latitude,p.coords.longitude],14); document.getElementById("status").textContent="Location obtained."; findDrivers(); },()=>document.getElementById("status").textContent="Location permission denied or unavailable.",{enableHighAccuracy:true,timeout:15000}); } async function findDrivers(){ const lat=parseFloat(document.getElementById("lat").value),lon=parseFloat(document.getElementById("lon").value); if(!Number.isFinite(lat)||!Number.isFinite(lon)){document.getElementById("status").textContent="Enter or obtain a valid location first.";return} document.getElementById("status").textContent="Searching for online drivers..."; try{ const r=await fetch(`/api/nearby-drivers?latitude=${encodeURIComponent(lat)}&longitude=${encodeURIComponent(lon)}&radius_km=50`); const d=await r.json(); markers.forEach(m=>map.removeLayer(m));markers=[]; const list=document.getElementById("driver-list"); if(!d.ok){list.textContent=d.message||"Search failed.";return} if(me)me.setLatLng([lat,lon]);else me=L.marker([lat,lon]).addTo(map).bindPopup("Your pickup/shop location"); if(!d.drivers.length){list.innerHTML="<p>No online drivers found within 50 km.</p>";document.getElementById("status").textContent="No nearby drivers are online.";return} list.innerHTML=""; d.drivers.forEach(driver=>{ const m=L.marker([driver.latitude,driver.longitude]).addTo(map).bindPopup(`<b>${escapeHtml(driver.name)}</b><br>${escapeHtml(driver.vehicle_type||"Vehicle")}<br>${driver.distance_km} km away`); markers.push(m); const div=document.createElement("div");div.className="card driver-card"; div.innerHTML=`<h3>${escapeHtml(driver.name)}</h3><p class="online">ONLINE</p><p><b>Vehicle:</b> ${escapeHtml(driver.vehicle_type||"Not specified")} ${escapeHtml(driver.vehicle_registration||"")}</p><p><b>Distance:</b> ${driver.distance_km} km</p><p><b>Phone:</b> ${escapeHtml(driver.phone||"")}</p><div class="actions"><button class="btn success" onclick="requestDriver('${driver.driver_id}')">Request Delivery</button><button class="btn secondary" onclick="map.setView([${driver.latitude},${driver.longitude}],16)">View on Map</button></div>`; list.appendChild(div); }); map.setView([lat,lon],13); document.getElementById("status").textContent=`Found ${d.drivers.length} online driver(s).`; }catch(e){document.getElementById("status").textContent="Unable to search drivers."} } function escapeHtml(s){return String(s??"").replace(/[&<>"']/g,m=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[m]))}
async function requestDriver(driverId){
 const lat=parseFloat(document.getElementById("lat").value),lon=parseFloat(document.getElementById("lon").value);
 const pickup=prompt("Pickup / shop location description:","My current location");
 if(pickup===null)return;
 const destination=prompt("Delivery destination:");
 if(!destination)return;
 const recipient=prompt("Recipient name:","");
 const phone=prompt("Recipient phone:","");
 const description=prompt("Package description:","");
 try{
  const r=await fetch("/api/delivery/request",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({
   driver_id:driverId,pickup_location:pickup,destination:destination,
   pickup_latitude:lat,pickup_longitude:lon,recipient_name:recipient||"",
   recipient_phone:phone||"",package_description:description||""
  })});
  const d=await r.json();
  alert(d.message||"Delivery request submitted.");
  if(d.ok)window.location.href="/deliveries";
 }catch(e){alert("Unable to send delivery request.")}
}
</script> """) @app.route("/api/nearby-drivers") @login_required def nearby_drivers(): lat=safe_float(request.args.get("latitude")) lon=safe_float(request.args.get("longitude")) radius=safe_float(request.args.get("radius_km")) or 50 radius=max(1,min(radius,200)) if lat is None or lon is None or not (-90<=lat<=90) or not (-180<=lon<=180): return jsonify({"ok":False,"message":"Valid latitude and longitude are required."}),400 if not table_exists("driver_locations"): return jsonify({"ok":False,"message":"The driver_locations table is not installed."}),503 latest=latest_driver_locations() results=[] now=datetime.now(timezone.utc) for driver_id,loc in latest.items(): if not loc.get("is_online"): continue dlat=safe_float(loc.get("latitude")); dlon=safe_float(loc.get("longitude")) if dlat is None or dlon is None: continue created=loc.get("created_at") # Do not show stale drivers older than 10 minutes. if created: try: dt=datetime.fromisoformat(str(created).replace("Z","+00:00")) if (now-dt).total_seconds()>600: continue except Exception: pass distance=haversine_km(lat,lon,dlat,dlon) if distance>radius: continue profile=first_row("driver_profiles",{"provider_id":driver_id}) provider=first_row("service_providers",{"id":driver_id}) or {} results.append({ "driver_id":str(driver_id), "name":first_nonempty(provider.get("full_name"),provider.get("name"),"Driver"), "phone":first_nonempty(provider.get("phone")), "vehicle_type":first_nonempty(profile.get("vehicle_type") if profile else ""), "vehicle_registration":first_nonempty(profile.get("vehicle_registration") if profile else ""), "latitude":dlat,"longitude":dlon, "accuracy":loc.get("accuracy"), "distance_km":round(distance,2), "updated_at":loc.get("created_at") }) results.sort(key=lambda x:x["distance_km"]) return jsonify({"ok":True,"drivers":results}) # ============================================================ # DELIVERY REQUEST / TRACKING
# ============================================================

def make_tracking_code():
    return "KOJA-" + datetime.now().strftime("%Y%m%d") + "-" + secrets.token_hex(3).upper()

@app.route("/api/delivery/request",methods=["POST"])
@login_required
def create_delivery_request():
    user=current_user()
    body=request.get_json(silent=True) or {}
    driver_id=clean(body.get("driver_id"))
    if not driver_id:
        return jsonify({"ok":False,"message":"Select a driver first."}),400

    driver=first_row("driver_profiles",{"provider_id":driver_id})
    if not driver:
        return jsonify({"ok":False,"message":"Driver profile not found."}),404

    lat=safe_float(body.get("pickup_latitude")); lon=safe_float(body.get("pickup_longitude"))
    tracking=make_tracking_code()

    payload={
        "id":str(uuid.uuid4()),
        "customer_id":user["id"],
        "user_id":user["id"],
        "driver_id":driver_id,
        "pickup_location":clean(body.get("pickup_location")),
        "destination":clean(body.get("destination")),
        "pickup_latitude":lat,
        "pickup_longitude":lon,
        "recipient_name":clean(body.get("recipient_name")),
        "recipient_phone":clean(body.get("recipient_phone")),
        "package_description":clean(body.get("package_description")),
        "package_weight":body.get("package_weight"),
        "delivery_fee":body.get("delivery_fee") or 0,
        "currency":"ZMW",
        "status":"requested",
        "tracking_code":tracking,
        "notes":clean(body.get("notes")),
        "created_at":utc_now(),"updated_at":utc_now()
    }

    row,error=db_insert("deliveries",payload)
    if error:
        minimal={
            "id":payload["id"],"customer_id":user["id"],"driver_id":driver_id,
            "pickup_location":payload["pickup_location"],
            "destination":payload["destination"],
            "recipient_name":payload["recipient_name"],
            "recipient_phone":payload["recipient_phone"],
            "package_description":payload["package_description"],
            "status":"requested","tracking_code":tracking
        }
        row,error=db_insert("deliveries",minimal)

    if error:
        return jsonify({"ok":False,"message":"Delivery request could not be created.","error":str(error)[:600]}),500

    log_activity("delivery_requested",f"Delivery {tracking} requested from driver {driver_id}.")
    return jsonify({"ok":True,"tracking_code":tracking,"message":f"Delivery request sent to the driver. Tracking code: {tracking}."})

@app.route("/deliveries",methods=["GET","POST"])
@login_required
def deliveries():
    user=current_user()

    if request.method=="POST":
        # Legacy/manual request. It creates an unassigned delivery,
        # after which the customer can search for a driver.
        tracking=make_tracking_code()
        payload={
            "id":str(uuid.uuid4()),"customer_id":user["id"],
            "pickup_location":clean(request.form.get("pickup_location")),
            "destination":clean(request.form.get("destination")),
            "recipient_name":clean(request.form.get("recipient_name")),
            "recipient_phone":clean(request.form.get("recipient_phone")),
            "package_description":clean(request.form.get("package_description")),
            "package_weight":request.form.get("package_weight") or None,
            "delivery_fee":request.form.get("delivery_fee") or 0,
            "currency":"ZMW","requested_date":request.form.get("requested_date") or None,
            "requested_time":request.form.get("requested_time") or None,
            "status":"requested","tracking_code":tracking,
            "notes":clean(request.form.get("notes")),"created_at":utc_now(),"updated_at":utc_now()
        }
        row,error=db_insert("deliveries",payload)
        if error:
            flash("Delivery could not be registered: "+str(error)[:600],"danger")
        else:
            flash(f"Delivery registered. Tracking code: {tracking}. Now choose a nearby driver.","success")
            return redirect(url_for("drivers"))
        return redirect(url_for("deliveries"))

    rows=db_select("deliveries",filters={"customer_id":user["id"]},order="created_at.desc",limit=100)
    return render_page("Deliveries",r""" <div class="hero"><h2>Delivery Service</h2><p>Use Nearby Drivers to see drivers around your shop/pickup location.</p><a class="btn success" href="{{ url_for('drivers') }}">Find Nearby Drivers</a></div> <div class="card"><h2>Create Delivery Without Selecting Driver Yet</h2> <form method="post"> <label>Pickup / Shop Location</label><input name="pickup_location" required> <label>Destination</label><input name="destination" required> <label>Recipient Name</label><input name="recipient_name" required> <label>Recipient Phone</label><input name="recipient_phone" required> <label>Package Description</label><textarea name="package_description"></textarea> <label>Package Weight (kg)</label><input type="number" step="0.01" name="package_weight"> <label>Delivery Fee (ZMW)</label><input type="number" step="0.01" name="delivery_fee"> <label>Requested Date</label><input type="date" name="requested_date"> <label>Requested Time</label><input type="time" name="requested_time"> <label>Notes</label><textarea name="notes"></textarea> <button type="submit">Create Delivery Request</button> </form></div> <div class="card"><h2>My Deliveries</h2> {% for d in rows %} <div class="card"><strong>{{ d.get("tracking_code") }}</strong> <p>{{ d.get("pickup_location") }} → {{ d.get("destination") }}</p> <p>Status: <span class="badge">{{ d.get("status") or "requested" }}</span></p> <p>Driver: {{ d.get("driver_id") or "Not selected" }}</p> <a class="btn" href="{{ url_for('track_delivery',tracking_code=d.get('tracking_code')) }}">Track Delivery</a> {% if not d.get("driver_id") %}<a class="btn success" href="{{ url_for('drivers') }}">Find Driver</a>{% endif %} </div> {% else %}<p>No deliveries registered.</p>{% endfor %} </div> """,rows=rows)

@app.route("/track/<tracking_code>")
@login_required
def track_delivery(tracking_code):
    delivery=first_row("deliveries",{"tracking_code":tracking_code})
    if not delivery: abort(404)
    return render_page("Track Delivery",r""" <div class="hero"><h2>Live Delivery Tracking</h2><p>Tracking code: <strong>{{ delivery.get("tracking_code") }}</strong></p></div> <div class="card"> <p><strong>Pickup:</strong> {{ delivery.get("pickup_location") }}</p> <p><strong>Destination:</strong> <span id="destination-text">{{ delivery.get("destination") }}</span></p> <p><strong>Status:</strong> <span id="delivery-status">{{ delivery.get("status") }}</span></p> <div class="grid"> <div class="stat"><div class="big" id="distance">—</div>Distance</div> <div class="stat"><div class="big" id="eta">—</div>ETA</div> <div class="stat"><div class="big" id="speed">—</div>Speed</div> </div> <div id="map"></div> <p id="tracking-status" class="small">Connecting to driver's live GPS...</p> <div class="actions"> <button class="btn secondary" onclick="centerDriver()">Center on Driver</button> <button class="btn" onclick="fitRoute()">Show Route</button> </div> </div> <script> const trackingCode={{ delivery.get("tracking_code")|tojson }}; const destination={{ delivery.get("destination")|tojson }}; let map=L.map("map").setView([-13.9626,28.3228],6); L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",{maxZoom:19,attribution:"&copy; OpenStreetMap contributors"}).addTo(map); let driverMarker=null,destinationMarker=null,routeLine=null,lastDriver=null,lastDestination=null,lastRouteAt=0; let driverIcon=L.divIcon({className:"koja-driver-icon",html:"<div style='font-size:30px;line-height:30px;transform-origin:center;'>🚚</div>",iconSize:[32,32],iconAnchor:[16,16]}); function setText(id,t){const el=document.getElementById(id);if(el)el.textContent=t} function centerDriver(){if(lastDriver)map.setView(lastDriver,17,{animate:true})} function fitRoute(){const pts=[];if(lastDriver)pts.push(lastDriver);if(lastDestination)pts.push(lastDestination);if(pts.length===2)map.fitBounds(L.latLngBounds(pts),{padding:[40,40]})} function km(m){return (m/1000).toFixed(1)+" km"}
function mins(sec){if(!Number.isFinite(sec))return "—";let m=Math.max(1,Math.round(sec/60));if(m<60)return m+" min";let h=Math.floor(m/60),r=m%60;return h+"h "+r+"m"} async function geocodeDestination(){ if(!destination)return; try{ const url="https://nominatim.openstreetmap.org/search?format=jsonv2&limit=1&q="+encodeURIComponent(destination); const r=await fetch(url,{headers:{"Accept":"application/json"}}); const a=await r.json(); if(!a.length){setText("tracking-status","Driver GPS connected. Destination could not be mapped automatically.");return} lastDestination=[parseFloat(a[0].lat),parseFloat(a[0].lon)]; destinationMarker=L.marker(lastDestination).addTo(map).bindPopup("Delivery destination"); setText("tracking-status","Destination mapped. Waiting for driver's live GPS..."); await updateRoute(true); }catch(e){setText("tracking-status","Live GPS is available, but destination mapping failed.")} } async function updateRoute(force=false){ if(!lastDriver||!lastDestination)return; if(!force && Date.now()-lastRouteAt<15000)return; lastRouteAt=Date.now(); try{ const a=lastDriver,b=lastDestination; const u=`https://router.project-osrm.org/route/v1/driving/${a[1]},${a[0]};${b[1]},${b[0]}?overview=full&geometries=geojson&steps=false`; const r=await fetch(u);const d=await r.json(); if(!d.routes||!d.routes.length)return; const route=d.routes[0]; const coords=route.geometry.coordinates.map(x=>[x[1],x[0]]); if(routeLine)routeLine.setLatLngs(coords);else routeLine=L.polyline(coords,{weight:5,opacity:.8}).addTo(map); setText("distance",km(route.distance)); setText("eta",mins(route.duration)); fitRoute(); }catch(e){ const R=6371,la1=a[0]*Math.PI/180,la2=b[0]*Math.PI/180,dla=(b[0]-a[0])*Math.PI/180,dlo=(b[1]-a[1])*Math.PI/180; const x=Math.sin(dla/2)**2+Math.cos(la1)*Math.cos(la2)*Math.sin(dlo/2)**2; const straight=2*R*Math.atan2(Math.sqrt(x),Math.sqrt(1-x)); setText("distance",straight.toFixed(1)+" km"); } } async function load(){ try{ const r=await fetch("/api/delivery/"+encodeURIComponent(trackingCode)+"/location"); const d=await r.json(); setText("delivery-status",d.status||""); if(!d.ok){setText("tracking-status",d.message||"No driver GPS available yet.");return} const p=[Number(d.latitude),Number(d.longitude)]; if(!Number.isFinite(p[0])||!Number.isFinite(p[1]))return; lastDriver=p; if(!driverMarker){driverMarker=L.marker(p,{icon:driverIcon}).addTo(map).bindPopup("Live driver location");map.setView(p,15)} else driverMarker.setLatLng(p); const heading=Number(d.heading); const node=driverMarker.getElement()?.querySelector("div"); if(node&&Number.isFinite(heading))node.style.transform="rotate("+heading+"deg)"; if(Number.isFinite(Number(d.speed)) && Number(d.speed)>=0)setText("speed",(Number(d.speed)*3.6).toFixed(0)+" km/h");else setText("speed","—"); const age=d.age_seconds!=null?Math.max(0,Math.round(d.age_seconds)):null; setText("tracking-status","LIVE — driver's GPS updated "+(age===null?"now":age+"s ago")+". Accuracy: "+(d.accuracy?Math.round(d.accuracy)+" m":"—")); await updateRoute(false); }catch(e){setText("tracking-status","Network connection lost. Retrying live GPS...")} } geocodeDestination(); load(); setInterval(load,5000); setInterval(()=>updateRoute(true),15000); </script> """,delivery=delivery)

@app.route("/api/delivery/<tracking_code>/location")
@login_required
def delivery_location(tracking_code):
    delivery=first_row("deliveries",{"tracking_code":tracking_code})
    if not delivery:
        return jsonify({"ok":False,"message":"Delivery not found."}),404

    user=current_user()
    # A customer can track their own delivery; admins/drivers can also monitor it.
    if not user.get("is_admin") and str(delivery.get("customer_id") or "") != str(user.get("id") or ""):
        assigned_driver=delivery.get("driver_id")
        provider=get_driver_provider(user.get("id"))
        provider_id=str(provider.get("id")) if provider else ""
        if not assigned_driver or provider_id != str(assigned_driver):
            return jsonify({"ok":False,"message":"You are not authorized to view this delivery."}),403

    driver_id=delivery.get("driver_id")
    locations=[]
    if driver_id:
        locations=db_select("driver_locations",filters={"driver_id":driver_id},order="created_at.desc",limit=1)
    if not locations:
        return jsonify({"ok":False,"message":"Driver has not shared a GPS location yet.","status":delivery.get("status")})

    loc=locations[0]
    updated=loc.get("created_at")
    age_seconds=None
    try:
        dt=datetime.fromisoformat(str(updated).replace("Z","+00:00"))
        age_seconds=max(0,(datetime.now(timezone.utc)-dt).total_seconds())
    except Exception:
        pass
    return jsonify({
        "ok":True,"latitude":loc.get("latitude"),"longitude":loc.get("longitude"),
        "accuracy":loc.get("accuracy"),"speed":loc.get("speed"),
        "heading":loc.get("heading"),"updated_at":updated,
        "age_seconds":age_seconds,"status":delivery.get("status")
    })

# ============================================================
# PROVIDER LOCATION / DOCTOR & TEACHER MAP
# ============================================================

@app.route("/provider-map/<provider_id>")
@login_required
def provider_map(provider_id):
    provider_type=request.args.get("provider_type","provider")
    return render_page("Provider Location",r""" <div class="hero"><h2>{{ provider_type|title }} Location</h2><p>Latest GPS position shared by this provider.</p></div> <div class="card"><div id="map"></div><p id="status">Loading provider location...</p></div> <script> const providerId={{ provider_id|tojson }},map=L.map("map").setView([-13.9626,28.3228],6); L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",{maxZoom:19,attribution:"&copy; OpenStreetMap contributors"}).addTo(map); let marker=null; async function update(){ try{ const r=await fetch("/api/provider/"+encodeURIComponent(providerId)+"/location"),d=await r.json(); if(!d.ok){document.getElementById("status").textContent=d.message||"No location available.";return} const p=[d.latitude,d.longitude]; if(!marker){marker=L.marker(p).addTo(map).bindPopup("Provider location");map.setView(p,15)}else marker.setLatLng(p); document.getElementById("status").textContent="Last update: "+d.updated_at; }catch(e){document.getElementById("status").textContent="Unable to load GPS position."} } update();setInterval(update,10000); </script> """,provider_id=provider_id,provider_type=provider_type)

@app.route("/api/provider/<provider_id>/location")
@login_required
def provider_location(provider_id):
    rows=db_select("driver_locations",filters={"driver_id":provider_id},order="created_at.desc",limit=1)
    if not rows:
        return jsonify({"ok":False,"message":"This provider has not shared a GPS location."})
    loc=rows[0]
    return jsonify({"ok":True,"latitude":loc.get("latitude"),"longitude":loc.get("longitude"),"accuracy":loc.get("accuracy"),"updated_at":loc.get("created_at")})

# ============================================================
# UNIVERSITIES
# ============================================================

@app.route("/universities")
@login_required
def universities():
    universities=db_select("universities",order="name.asc",limit=200)
    return render_page("Universities",r""" <div class="hero"><h2>University Applications</h2><p>Select the university, programme, intake/year and review requirements.</p></div> <div class="card"> {% if universities %}<div class="grid"> {% for university in universities %} <div class="card"><h3>{{ university.get("name") or university.get("university_name") or "University" }}</h3> <p>{{ university.get("location") or university.get("description") or "" }}</p> <a class="btn" href="{{ url_for('university_apply',university_id=university.get('id')) }}">Apply</a></div> {% endfor %} </div>{% else %}<p>No universities are currently loaded into the universities table.</p>{% endif %} </div> """,universities=universities)

@app.route("/university/apply/<university_id>",methods=["GET","POST"])
@login_required
def university_apply(university_id):
    user=current_user()
    university=first_row("universities",{"id":university_id})
    if not university: abort(404)
    programmes=db_select("university_programmes",filters={"university_id":university_id},order="name.asc",limit=500)
    requirements=db_select("university_application_requirements",filters={"university_id":university_id},limit=500)

    if request.method=="POST":
        programme_id=request.form.get("programme_id")
        year=request.form.get("academic_year")
        intake=clean(request.form.get("intake"))
        payload={
            "id":str(uuid.uuid4()),"user_id":user["id"],"university_id":university_id,
            "programme_id":programme_id,"academic_year":year,"intake":intake or None,
            "full_name":user["name"],"email":user["email"],"phone":user.get("phone"),
            "status":"draft","created_at":utc_now()
        }
        row,error=db_insert("university_applications",payload)
        if error:
            minimal={k:payload[k] for k in ("id","user_id","university_id","programme_id","academic_year")}
            row,error=db_insert("university_applications",minimal)
        if error: flash("Application could not be created: "+str(error)[:600],"danger")
        else: flash("University application started successfully.","success")
        return redirect(url_for("universities"))

    return render_page("University Application",r""" <div class="card"><h2>{{ university.get("name") or university.get("university_name") }}</h2> <form method="post"> <label>Programme</label><select name="programme_id" required><option value="">Select programme</option> {% for p in programmes %}<option value="{{ p.get('id') }}">{{ p.get("name") or p.get("programme_name") or p.get("title") }}</option>{% endfor %} </select> <label>Academic Year</label><select name="academic_year"><option>2026/2027</option><option>2027/2028</option></select> <label>Intake</label><select name="intake"><option>January</option><option>May</option><option>September</option><option>Other</option></select> <button type="submit">Start Application</button> </form></div> <div class="card"><h3>Application Requirements</h3> {% for r in requirements %}<div class="card"><strong>{{ r.get("title") or r.get("requirement") or "Requirement" }}</strong><p>{{ r.get("description") or r.get("details") or "" }}</p></div> {% else %}<p>No specific requirements have been entered for this university yet.</p>{% endfor %} </div> """,university=university,programmes=programmes,requirements=requirements)

# ============================================================
# GOOGLE SEARCH & DISTRIBUTION
# ============================================================

PUBLIC_INDEX_ROUTES = [
    "/",
    "/services",
    "/questions",
    "/assignments",
    "/tracking",
    "/drivers",
]

GSC_SCOPE = "https://www.googleapis.com/auth/webmasters.readonly"
GSC_WRITE_SCOPE = "https://www.googleapis.com/auth/webmasters"
GSC_SEARCH_API = "https://www.googleapis.com/webmasters/v3"
GSC_INSPECTION_API = "https://searchconsole.googleapis.com/v1/urlInspection/index:inspect"


def gsc_authorized_session(write=False):
    """Build an authenticated Google Search Console session from a Render secret."""
    if not GSC_SERVICE_ACCOUNT_JSON:
        return None, "GSC_SERVICE_ACCOUNT_JSON is not configured."
    try:
        import json
        from google.oauth2 import service_account
        from google.auth.transport.requests import AuthorizedSession
        info = json.loads(GSC_SERVICE_ACCOUNT_JSON)
        scope = GSC_WRITE_SCOPE if write else GSC_SCOPE
        credentials = service_account.Credentials.from_service_account_info(info, scopes=[scope])
        return AuthorizedSession(credentials), None
    except ImportError:
        return None, "google-auth is not installed. Add google-auth to requirements.txt and redeploy."
    except Exception as exc:
        logger.exception("GSC credentials error")
        return None, f"Invalid GSC_SERVICE_ACCOUNT_JSON: {str(exc)[:400]}"


def google_search_console_report(days=28, dimension="query"):
    """Fetch real Search Console performance data."""
    result = {"connected": False, "message": "Google Search Console API is not configured.", "rows": [], "start": None, "end": None}
    session_http, error = gsc_authorized_session(False)
    if error:
        result["message"] = error
        return result
    try:
        end = datetime.now(timezone.utc).date()
        start = end - timedelta(days=max(1, min(int(days), 90)))
        site = quote(GSC_SITE_URL, safe="")
        endpoint = f"{GSC_SEARCH_API}/sites/{site}/searchAnalytics/query"
        payload = {
            "startDate": start.isoformat(),
            "endDate": end.isoformat(),
            "dimensions": [dimension],
            "rowLimit": 100,
            "dataState": "final"
        }
        response = session_http.post(endpoint, json=payload, timeout=25)
        if not response.ok:
            result["message"] = f"Google API HTTP {response.status_code}: {response.text[:500]}"
            return result
        rows = []
        for row in response.json().get("rows", []):
            key = (row.get("keys") or ["Unknown"])[0]
            rows.append({
                "key": key,
                "clicks": round(float(row.get("clicks", 0)), 2),
                "impressions": round(float(row.get("impressions", 0)), 2),
                "ctr": round(float(row.get("ctr", 0)) * 100, 2),
                "position": round(float(row.get("position", 0)), 2)
            })
        result.update({"connected": True, "message": "Connected to Google Search Console.", "rows": rows, "start": start.isoformat(), "end": end.isoformat()})
        return result
    except Exception as exc:
        logger.exception("Google Search Console performance error")
        result["message"] = f"Search Console error: {str(exc)[:500]}"
        return result


def google_search_console_daily(days=28):
    """Return daily real Search Console performance for a chart."""
    result = google_search_console_report(days, "date")
    if result.get("connected"):
        result["rows"] = sorted(result["rows"], key=lambda x: x["key"])
    return result


def google_search_console_inspect(url):
    """Run Google's URL Inspection API for one URL."""
    session_http, error = gsc_authorized_session(False)
    if error:
        return {"ok": False, "message": error}
    try:
        payload = {"inspectionUrl": url, "siteUrl": GSC_SITE_URL, "languageCode": "en-US"}
        response = session_http.post(GSC_INSPECTION_API, json=payload, timeout=25)
        data = response.json() if response.content else {}
        if not response.ok:
            return {"ok": False, "message": f"Google API HTTP {response.status_code}: {response.text[:500]}", "data": data}
        result = data.get("inspectionResult", {})
        index_status = result.get("indexStatusResult", {})
        return {
            "ok": True,
            "message": "URL inspection completed.",
            "data": data,
            "verdict": index_status.get("verdict", "UNKNOWN"),
            "coverage": index_status.get("coverageState", "Unknown"),
            "indexing": index_status.get("indexingState", "Unknown"),
            "canonical": index_status.get("googleCanonical", "Unknown"),
            "last_crawl": index_status.get("lastCrawlTime", "Unknown"),
            "robots": index_status.get("robotsTxtState", "Unknown"),
        }
    except Exception as exc:
        logger.exception("Google URL inspection error")
        return {"ok": False, "message": f"URL inspection error: {str(exc)[:500]}"}


def google_sitemaps():
    """List sitemaps known to the Search Console property."""
    session_http, error = gsc_authorized_session(False)
    if error:
        return {"ok": False, "message": error, "sitemaps": []}
    try:
        site = quote(GSC_SITE_URL, safe="")
        response = session_http.get(f"{GSC_SEARCH_API}/sites/{site}/sitemaps", timeout=25)
        data = response.json() if response.content else {}
        if not response.ok:
            return {"ok": False, "message": f"Google API HTTP {response.status_code}: {response.text[:500]}", "sitemaps": []}
        return {"ok": True, "message": "Sitemaps loaded from Google Search Console.", "sitemaps": data.get("sitemap", [])}
    except Exception as exc:
        return {"ok": False, "message": f"Sitemap API error: {str(exc)[:500]}", "sitemaps": []}


def google_submit_sitemap(sitemap_url):
    """Submit/update a sitemap in the verified Search Console property."""
    session_http, error = gsc_authorized_session(True)
    if error:
        return False, error
    try:
        site = quote(GSC_SITE_URL, safe="")
        sm = quote(sitemap_url, safe="")
        response = session_http.put(f"{GSC_SEARCH_API}/sites/{site}/sitemaps/{sm}", timeout=25)
        if response.status_code in (200, 204):
            return True, "Sitemap submitted to Google Search Console."
        return False, f"Google API HTTP {response.status_code}: {response.text[:500]}"
    except Exception as exc:
        return False, f"Sitemap submission error: {str(exc)[:500]}"


@app.route("/admin/search-distribution", methods=["GET", "POST"])
@admin_required
def admin_search_distribution():
    days_raw = request.values.get("days", "28")
    try:
        days = max(7, min(int(days_raw), 90))
    except (ValueError, TypeError):
        days = 28

    inspect_result = None
    submit_message = None
    if request.method == "POST":
        action = request.form.get("action")
        if action == "inspect":
            inspect_url = (request.form.get("inspect_url") or SITE_URL + "/").strip()
            if not inspect_url.startswith(("http://", "https://")):
                inspect_result = {"ok": False, "message": "Enter a complete URL beginning with https://"}
            else:
                inspect_result = google_search_console_inspect(inspect_url)
        elif action == "submit_sitemap":
            ok, msg = google_submit_sitemap(f"{SITE_URL}/sitemap.xml")
            submit_message = (ok, msg)

    query_report = google_search_console_report(days, "query")
    page_report = google_search_console_report(days, "page")
    daily_report = google_search_console_daily(days)
    sitemap_report = google_sitemaps()
    indexed_candidates = list(dict.fromkeys(PUBLIC_INDEX_ROUTES))

    return render_page("Google Search & Distribution", r""" <div class="hero"> <h2>🔎 Google Search & Distribution</h2> <p>Real Google Search Console controls and performance data for KOJA AFRICA.</p> <div class="actions"> <a class="btn" href="https://search.google.com/search-console" target="_blank" rel="noopener">Open Google Search Console</a> <a class="btn secondary" href="{{ url_for('sitemap_xml') }}" target="_blank">View Sitemap</a> <a class="btn secondary" href="{{ url_for('robots_txt') }}" target="_blank">View robots.txt</a> </div> </div> <div class="grid"> <div class="stat"><div class="big">{{ 'CONNECTED' if query_report.connected else 'NOT CONNECTED' }}</div>Search Console API</div> <div class="stat"><div class="big">{{ indexed_candidates|length }}</div>Public sitemap URLs</div> <div class="stat"><div class="big">{{ query_report.rows|length if query_report.connected else '—' }}</div>Search queries</div> <div class="stat"><div class="big">{{ days }}</div>Days</div> </div> <div class="card"> <h3>📊 Search performance</h3> <p class="small">{{ query_report.message }}</p> {% if query_report.connected %} <div class="grid"> {% set total_clicks = query_report.rows|sum(attribute='clicks') %} {% set total_impressions = query_report.rows|sum(attribute='impressions') %} <div class="stat"><div class="big">{{ '%.0f'|format(total_clicks) }}</div>Clicks in returned query rows</div> <div class="stat"><div class="big">{{ '%.0f'|format(total_impressions) }}</div>Impressions in returned query rows</div> <div class="stat"><div class="big">{{ daily_report.rows|length }}</div>Days with data</div> </div> {% else %} <p>Connect the property to show real clicks, impressions, CTR and average position. Google requires authorized access to the Search Console property for the Search Analytics API.</p> {% endif %} </div> {% if query_report.connected %} <div class="card"> <div class="actions"><h3 style="margin-right:auto">Top Search Queries</h3><a class="btn secondary" href="{{ url_for('admin_search_distribution',days=7) }}">7 days</a><a class="btn secondary" href="{{ url_for('admin_search_distribution',days=28) }}">28 days</a><a class="btn secondary" href="{{ url_for('admin_search_distribution',days=90) }}">90 days</a></div> <table><tr><th>Query</th><th>Clicks</th><th>Impressions</th><th>CTR</th><th>Avg. position</th></tr> {% for r in query_report.rows %}<tr><td>{{ r.key }}</td><td>{{ r.clicks }}</td><td>{{ r.impressions }}</td><td>{{ r.ctr }}%</td><td>{{ r.position }}</td></tr>{% else %}<tr><td colspan="5">No search-query data is available.</td></tr>{% endfor %}</table> </div> <div class="card"><h3>Top Pages from Google Search</h3> <table><tr><th>Page</th><th>Clicks</th><th>Impressions</th><th>CTR</th><th>Avg. position</th></tr> {% for r in page_report.rows %}<tr><td>{{ r.key }}</td><td>{{ r.clicks }}</td><td>{{ r.impressions }}</td><td>{{ r.ctr }}%</td><td>{{ r.position }}</td></tr>{% else %}<tr><td colspan="5">No page data is available.</td></tr>{% endfor %}</table></div> <div class="card"><h3>Daily Search Performance</h3><table><tr><th>Date</th><th>Clicks</th><th>Impressions</th><th>CTR</th><th>Avg. position</th></tr> {% for r in daily_report.rows %}<tr><td>{{ r.key }}</td><td>{{ r.clicks }}</td><td>{{ r.impressions }}</td><td>{{ r.ctr }}%</td><td>{{ r.position }}</td></tr>{% endfor %}</table></div> {% endif %} <div class="card"> <h3>🔍 URL Inspection</h3> <p>Enter a KOJA URL and send it to Google's real URL Inspection API.</p> <form method="post"> <input type="hidden" name="action" value="inspect"> <input name="inspect_url" value="{{ request.form.get('inspect_url', SITE_URL + '/') }}" placeholder="https://koja-africa.onrender.com/"> <button class="btn" type="submit">Inspect URL</button> </form> {% if inspect_result %} <div class="alert"><strong>{{ inspect_result.message }}</strong></div> {% if inspect_result.ok %}<table><tr><th>Verdict</th><td>{{ inspect_result.verdict }}</td></tr><tr><th>Coverage</th><td>{{ inspect_result.coverage }}</td></tr><tr><th>Indexing</th><td>{{ inspect_result.indexing }}</td></tr><tr><th>Google canonical</th><td>{{ inspect_result.canonical }}</td></tr><tr><th>Last crawl</th><td>{{ inspect_result.last_crawl }}</td></tr><tr><th>Robots</th><td>{{ inspect_result.robots }}</td></tr></table>{% endif %} {% endif %} </div> <div class="card"> <h3>🗺️ Sitemap distribution</h3> <p>Your sitemap: <a href="{{ url_for('sitemap_xml') }}" target="_blank">{{ SITE_URL }}/sitemap.xml</a></p> <form method="post"><input type="hidden" name="action" value="submit_sitemap"><button class="btn success" type="submit">Submit sitemap to Google</button></form> {% if submit_message %}<div class="alert">{{ submit_message[1] }}</div>{% endif %} {% if sitemap_report.ok %}<h4>Sitemaps known to Google</h4><table><tr><th>Path</th><th>Last submitted</th><th>Last downloaded</th><th>Warnings</th><th>Errors</th></tr>{% for sm in sitemap_report.sitemaps %}<tr><td>{{ sm.path }}</td><td>{{ sm.lastSubmitted }}</td><td>{{ sm.lastDownloaded }}</td><td>{{ sm.warnings }}</td><td>{{ sm.errors }}</td></tr>{% else %}<tr><td colspan="5">No sitemap is currently listed by the API.</td></tr>{% endfor %}</table>{% else %}<p class="small">{{ sitemap_report.message }}</p>{% endif %} </div> <div class="card"><h3>🚀 Public distribution</h3><table><tr><th>URL</th><th>Status</th></tr>{% for u in indexed_candidates %}<tr><td><a href="{{ SITE_URL }}{{ u }}" target="_blank">{{ SITE_URL }}{{ u }}</a></td><td>Included in sitemap</td></tr>{% endfor %}</table></div> <div class="card"><h3>⚙️ One-time Google connection</h3><ol><li>Create/select a Google Cloud project.</li><li>Enable the Search Console API.</li><li>Create a service account and download its JSON credentials.</li><li>Add that service-account email as an owner/full user of the verified <strong>{{ GSC_SITE_URL }}</strong> Search Console property.</li><li>Put the JSON contents into the Render environment variable <code>GSC_SERVICE_ACCOUNT_JSON</code>.</li><li>Set <code>GSC_SITE_URL=https://koja-africa.onrender.com/</code>.</li><li>Redeploy KOJA AFRICA.</li></ol><p class="small">The credentials stay server-side; never put the service-account JSON in HTML or browser JavaScript.</p></div> """, query_report=query_report, page_report=page_report, daily_report=daily_report, days=days, indexed_candidates=indexed_candidates, inspect_result=inspect_result, submit_message=submit_message, sitemap_report=sitemap_report, SITE_URL=SITE_URL, GSC_SITE_URL=GSC_SITE_URL)


@app.route("/robots.txt")
def robots_txt():
    lines = [
        "User-agent: *",
        "Allow: /",
        "Disallow: /admin",
        "Disallow: /login",
        "Disallow: /register",
        "Disallow: /dashboard",
        "Disallow: /api/",
        f"Sitemap: {SITE_URL}/sitemap.xml",
    ]
    return ("\n".join(lines) + "\n", 200, {"Content-Type": "text/plain; charset=utf-8"})


@app.route("/sitemap.xml")
def sitemap_xml():
    urls = []
    for route in PUBLIC_INDEX_ROUTES:
        urls.append(f"<url><loc>{SITE_URL}{route}</loc><changefreq>weekly</changefreq><priority>{'1.0' if route == '/' else '0.7'}</priority></url>")
    xml = '<?xml version="1.0" encoding="UTF-8"?>' + '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + ''.join(urls) + '</urlset>'
    return (xml, 200, {"Content-Type": "application/xml; charset=utf-8"})

# ============================================================
# ADMIN
# ============================================================

@app.route("/admin")
@admin_required
def admin():
    tables=["profiles","questions","assignments","farmer_registrations","doctor_profiles","teacher_profiles","driver_profiles","driver_locations","deliveries","appointments","universities","university_applications","activity_logs"]
    counts={}
    for table in tables:
        counts[table]=len(db_select(table,limit=1000))
    return render_page("Admin Dashboard",r""" <div class="hero"><h2>KOJA Administrator</h2><p>System management dashboard.</p></div> <div class="grid">{% for name,count in counts.items() %}<div class="stat"><div class="big">{{ count }}</div>{{ name }}</div>{% endfor %}</div> <div class="card"><h3>Management</h3> <div class="actions"> <a class="btn" href="{{ url_for('admin_users') }}">Users</a> <a class="btn" href="{{ url_for('admin_drivers') }}">Drivers</a> <a class="btn" href="{{ url_for('admin_deliveries') }}">Deliveries</a> <a class="btn success" href="{{ url_for('admin_live_tracking') }}">🚚 Live GPS Tracking</a> <a class="btn" href="{{ url_for('admin_appointments') }}">Appointments</a> <a class="btn success" href="{{ url_for('admin_search_distribution') }}">🔎 Google Search & Distribution</a> </div></div> """,counts=counts)

@app.route("/admin/users")
@admin_required
def admin_users():
    rows=db_select("profiles",order="created_at.desc",limit=300)
    return render_page("Admin Users",r""" <div class="card"><h2>Users</h2><table><tr><th>Name</th><th>Email</th><th>Phone</th><th>Role</th><th>Admin</th></tr> {% for u in rows %}<tr><td>{{ u.get("full_name") or u.get("name") }}</td><td>{{ u.get("email") }}</td><td>{{ u.get("phone") or "" }}</td><td>{{ u.get("role") or "" }}</td><td>{{ "Yes" if u.get("is_admin") else "No" }}</td></tr>{% endfor %} </table></div> """,rows=rows)

@app.route("/admin/drivers")
@admin_required
def admin_drivers():
    rows=db_select("driver_profiles",order="created_at.desc",limit=300)
    return render_page("Admin Drivers",r""" <div class="card"><h2>Drivers</h2><table><tr><th>Name</th><th>Phone</th><th>Vehicle</th><th>Number</th><th>Provider ID</th></tr> {% for d in rows %}<tr><td>{{ d.get("full_name") or d.get("driver_name") }}</td><td>{{ d.get("phone") }}</td><td>{{ d.get("vehicle_type") }}</td><td>{{ d.get("vehicle_number") }}</td><td>{{ d.get("provider_id") or d.get("user_id") }}</td></tr>{% endfor %} </table></div> """,rows=rows)

@app.route("/admin/live-tracking")
@admin_required
def admin_live_tracking():
    return render_page("Admin Live GPS Tracking", r""" <div class="hero"><h2>🚚 Live Delivery GPS</h2> <p>Real-time driver locations received from active KOJA driver phones.</p></div> <div class="card"><div id="map" style="height:520px;min-height:420px"></div> <p id="status" class="small">Loading live drivers...</p></div> <script> const map=L.map("map").setView([-13.9626,28.3228],6); L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",{maxZoom:19,attribution:"&copy; OpenStreetMap contributors"}).addTo(map); const markers={}; function esc(v){return String(v??"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/\"/g,"&quot;").replace(/'/g,"&#39;");}
async function refresh(){
 try{
  const r=await fetch("{{ url_for('admin_live_drivers_api') }}",{cache:"no-store"});
  const d=await r.json();
  if(!d.ok){document.getElementById("status").textContent=d.message||"Unable to load GPS.";return;}
  const seen={};
  d.drivers.forEach(x=>{
    seen[x.driver_id]=true; const p=[x.latitude,x.longitude];
    if(!markers[x.driver_id]) markers[x.driver_id]=L.marker(p).addTo(map);
    else markers[x.driver_id].setLatLng(p);
    markers[x.driver_id].bindPopup("<b>"+esc(x.name)+"</b><br>"+esc(x.vehicle_type||"Vehicle")+"<br>Accuracy: "+esc(x.accuracy||"—")+" m<br>Updated: "+esc(x.updated_at||"recently"));
  });
  Object.keys(markers).forEach(id=>{if(!seen[id]){map.removeLayer(markers[id]);delete markers[id];}});
  document.getElementById("status").textContent=d.drivers.length+" driver(s) online. Last refresh: "+new Date().toLocaleTimeString();
 }catch(e){document.getElementById("status").textContent="Network error while loading live GPS.";}
}
refresh(); setInterval(refresh,5000);
</script> """) @app.route("/api/admin/live-drivers") @admin_required def admin_live_drivers_api(): if not table_exists("driver_locations"): return jsonify({"ok":False,"message":"driver_locations table is not available.","drivers":[]}),503 locations=latest_driver_locations() now=datetime.now(timezone.utc) result=[] for loc in locations: if not loc.get("is_online"): continue try: ts=datetime.fromisoformat(str(loc.get("created_at")).replace("Z","+00:00")) if ts.tzinfo is None: ts=ts.replace(tzinfo=timezone.utc) age=(now-ts).total_seconds() if age > 120: continue except Exception: age=None provider=first_row("driver_profiles", {"provider_id":str(loc.get("driver_id"))}) name=(provider or {}).get("full_name") or (provider or {}).get("driver_name") or "Driver" result.append({"driver_id":str(loc.get("driver_id")),"name":name,"vehicle_type":(provider or {}).get("vehicle_type"),"latitude":loc.get("latitude"),"longitude":loc.get("longitude"),"accuracy":loc.get("accuracy"),"updated_at":loc.get("created_at"),"age_seconds":age}) return jsonify({"ok":True,"drivers":result}) @app.route("/admin/deliveries") @admin_required def admin_deliveries(): rows=db_select("deliveries",order="created_at.desc",limit=300) return render_page("Admin Deliveries",r"""
<div class="card"><h2>Deliveries</h2><table><tr><th>Tracking</th><th>Customer</th><th>Pickup</th><th>Destination</th><th>Driver</th><th>Status</th><th>GPS</th></tr> {% for d in rows %}<tr><td>{{ d.get("tracking_code") }}</td><td>{{ d.get("customer_id") }}</td><td>{{ d.get("pickup_location") }}</td><td>{{ d.get("destination") }}</td><td>{{ d.get("driver_id") or "Unassigned" }}</td><td>{{ d.get("status") }}</td><td><a class="btn secondary" href="{{ url_for('track_delivery',tracking_code=d.get('tracking_code')) }}" target="_blank">Track GPS</a></td></tr>{% endfor %} </table></div> """,rows=rows)

@app.route("/admin/appointments")
@admin_required
def admin_appointments():
    rows=db_select("appointments",order="created_at.desc",limit=300)
    return render_page("Admin Appointments",r""" <div class="card"><h2>Appointments</h2><table><tr><th>Date</th><th>Client</th><th>Provider</th><th>Type</th><th>Status</th></tr> {% for a in rows %}<tr><td>{{ a.get("appointment_date") }}</td><td>{{ a.get("client_id") }}</td><td>{{ a.get("provider_id") }}</td><td>{{ a.get("appointment_type") }}</td><td>{{ a.get("status") }}</td></tr>{% endfor %} </table></div> """,rows=rows)

# ============================================================
# ERROR HANDLERS
# ============================================================

@app.errorhandler(404)
def not_found(error):
    return render_page("Not Found",r""" <div class="card"><h2>Page Not Found</h2><p>The requested page does not exist.</p><a class="btn" href="{{ url_for('home') }}">Return Home</a></div> """),404

@app.errorhandler(413)
def too_large(error):
    return render_page("File Too Large",r""" <div class="card"><h2>File Too Large</h2><p>The maximum upload size is {{ max_mb }} MB.</p></div> """,max_mb=MAX_UPLOAD_MB),413

@app.errorhandler(500)
def internal_error(error):
    logger.exception("Unhandled application error")
    return render_page("Server Error",r""" <div class="card"><h2>KOJA AFRICA Server Error</h2><p>The server encountered an unexpected error. Check Render logs for details.</p><a class="btn" href="{{ url_for('home') }}">Return Home</a></div> """),500

@app.before_request
def before_request():
    # Deliberately empty. Never connect to Supabase at startup.
    pass

@app.context_processor
def inject_globals():
    return {"APP_NAME":APP_NAME,"APP_TAGLINE":APP_TAGLINE,"SITE_URL":SITE_URL}

# ============================================================
# LOCAL / RENDER START
# ============================================================

if __name__=="__main__":
    port=int(os.getenv("PORT","5000"))
    app.run(host="0.0.0.0",port=port,debug=False)

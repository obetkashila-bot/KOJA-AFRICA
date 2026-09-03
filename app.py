import os
import io
import uuid
import math
import secrets
import logging
import smtplib
from email.message import EmailMessage
import json
import re
from datetime import datetime, timezone, timedelta
from functools import wraps
from urllib.parse import quote, unquote

import requests
from dotenv import load_dotenv
from flask import (
    Flask, request, redirect, url_for, session,
    render_template_string, flash, send_file, jsonify, abort
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from werkzeug.middleware.proxy_fix import ProxyFix

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
# Render terminates HTTPS at the proxy; trust forwarded host/proto headers.
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
app.secret_key = os.getenv(
    "SECRET_KEY",
    os.getenv("FLASK_SECRET_KEY", secrets.token_hex(32))
)
app.config["MAX_CONTENT_LENGTH"] = 15 * 1024 * 1024
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.getenv("SESSION_COOKIE_SECURE", "true").lower() not in ("0", "false", "no")
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=7)

# Lightweight production rate limiting without an extra dependency.
_rate_hits = {}
def _rate_limited(key, limit, window=60):
    now = datetime.now(timezone.utc).timestamp()
    bucket = _rate_hits.get(key, [])
    bucket = [t for t in bucket if now - t < window]
    if len(bucket) >= limit:
        _rate_hits[key] = bucket
        return True
    bucket.append(now)
    _rate_hits[key] = bucket
    # Prevent unbounded memory growth on long-running instances.
    if len(_rate_hits) > 5000:
        oldest = sorted(_rate_hits.items(), key=lambda kv: kv[1][-1] if kv[1] else 0)[:1000]
        for k, _ in oldest:
            _rate_hits.pop(k, None)
    return False

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_KEY = (
    os.getenv("SUPABASE_SERVICE_KEY", "")
    or os.getenv("SUPABASE_KEY", "")
)
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
FLW_SECRET_KEY = os.getenv("FLW_SECRET_KEY", "").strip()
FLW_BASE_URL = "https://api.flutterwave.com/v3"


STORAGE_BUCKET = os.getenv(
    "SUPABASE_STORAGE_BUCKET",
    "koja-files"
)

APP_NAME = "KOJA AFRICA"
APP_VERSION = "2026.09.03-RESEARCH-V2"
APP_TAGLINE = "Knowledge • Questions • Answers"
MAX_UPLOAD_MB = 15

# Email delivery (server-side only; never expose SMTP passwords to the browser)
EMAIL_PROVIDER = os.getenv("EMAIL_PROVIDER", "smtp").strip().lower()
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com").strip()
SMTP_PORT = int(os.getenv("SMTP_PORT", "587") or 587)
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "").strip()
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "").strip()
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USERNAME).strip()
SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "true").strip().lower() not in ("0", "false", "no")

# Google Search & Distribution
SITE_URL = os.getenv("SITE_URL", "https://koja-africa.onrender.com").rstrip("/")
GSC_SITE_URL = os.getenv("GSC_SITE_URL", SITE_URL)
GSC_SERVICE_ACCOUNT_JSON = os.getenv("GSC_SERVICE_ACCOUNT_JSON", "").strip()


ALLOWED_EXTENSIONS = {
    "pdf", "doc", "docx", "txt",
    "jpg", "jpeg", "png", "webp", "mp4", "webm", "mov"
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
    """
    Optional compatibility path for accounts created in Supabase Auth.
    Set SUPABASE_ANON_KEY in Render for this path.
    """
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

def email_configured():
    return bool(SMTP_HOST and SMTP_USERNAME and SMTP_PASSWORD and SMTP_FROM)

def send_email_with_attachment(to_email, subject, body, attachment_bytes, filename, mime_type="application/pdf"):
    """Send a server-side email with an assignment answer PDF attached.

    Supports normal SMTP and Gmail SMTP. Gmail accounts should use a Google
    App Password, not the normal Gmail account password.
    """
    to_email = clean(to_email).lower()
    if not to_email or "@" not in to_email:
        return False, "A valid recipient email address is required."
    if not email_configured():
        return False, "Email is not configured. Set SMTP_USERNAME, SMTP_PASSWORD and SMTP_FROM in Render environment variables."
    if not attachment_bytes:
        return False, "The answer PDF is empty or missing."
    try:
        msg = EmailMessage()
        msg["From"] = SMTP_FROM
        msg["To"] = to_email
        msg["Subject"] = subject or "KOJA AFRICA Assignment Answer"
        msg.set_content(body or "Please find your KOJA AFRICA assignment answer attached as a PDF.")
        maintype, subtype = (mime_type or "application/pdf").split("/", 1) if "/" in (mime_type or "") else ("application", "pdf")
        msg.add_attachment(attachment_bytes, maintype=maintype, subtype=subtype, filename=filename or "KOJA-Answer.pdf")

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as server:
            server.ehlo()
            if SMTP_USE_TLS:
                server.starttls()
                server.ehlo()
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.send_message(msg)
        return True, None
    except Exception as exc:
        logger.exception("Assignment email send failed")
        return False, str(exc)

def send_plain_email(to_email, subject, body):
    to_email = clean(to_email)
    if not to_email or "@" not in to_email:
        return False, "A valid recipient email is required."
    if not email_configured():
        return False, "Email is not configured on the server."
    try:
        msg = EmailMessage()
        msg["Subject"] = subject or "KOJA AFRICA Notification"
        msg["From"] = SMTP_FROM
        msg["To"] = to_email
        msg.set_content(body or "KOJA AFRICA notification")
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as smtp:
            if SMTP_USE_TLS:
                smtp.starttls()
            smtp.login(SMTP_USERNAME, SMTP_PASSWORD)
            smtp.send_message(msg)
        return True, None
    except Exception as exc:
        logger.exception("Plain email failed")
        return False, str(exc)

def get_assignment_recipient(assignment):
    """Resolve the assignment owner's email safely from a dict or list response."""
    if isinstance(assignment, list):
        assignment = assignment[0] if assignment else {}
    if not isinstance(assignment, dict):
        assignment = {}
    owner_id = assignment_owner_id(assignment)
    if owner_id:
        user = first_row("profiles", {"id": owner_id})
        if user and clean(user.get("email")):
            return clean(user.get("email")).lower(), user
    # Fallback for legacy assignments where only an email was retained.
    email = clean(assignment.get("email") or assignment.get("student_email"))
    return (email.lower() if email else ""), None

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

BASE_HTML = r"""
<!doctype html>
<html lang="en" data-koja-theme="system">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">
<meta name="description" content="{{ meta_description or 'KOJA AFRICA — knowledge, questions, answers, research, assignments, documents, professional services and delivery services.' }}">
<meta name="robots" content="{% if request.path.startswith('/admin') or request.path.startswith('/api/') or request.path in ['/login','/register','/dashboard'] %}noindex,nofollow{% else %}index,follow,max-image-preview:large{% endif %}">
<meta name="googlebot" content="{% if request.path.startswith('/admin') or request.path.startswith('/api/') or request.path in ['/login','/register','/dashboard'] %}noindex,nofollow{% else %}index,follow{% endif %}">
<meta name="google-site-verification" content="u4nfIf5MfXm0iVvECSQeYAov4Tz4601ayY5kYzNc4ko">
<link rel="canonical" href="{{ SITE_URL }}{{ request.path }}">
<link rel="icon" type="image/svg+xml" href="{{ url_for('static', filename='favicon.svg') }}">
<link rel="icon" type="image/png" sizes="192x192" href="{{ url_for('static', filename='favicon-192.png') }}">
<link rel="apple-touch-icon" href="{{ url_for('static', filename='favicon-192.png') }}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="KOJA AFRICA">
<meta property="og:title" content="{{ title or 'KOJA AFRICA' }}">
<meta property="og:description" content="{{ meta_description or 'KOJA AFRICA — knowledge, questions, answers, research, assignments, documents, professional services and delivery services.' }}">
<meta name="twitter:card" content="summary">
<meta name="twitter:title" content="{{ title or 'KOJA AFRICA' }}">
<meta name="twitter:description" content="{{ meta_description or 'KOJA AFRICA — knowledge, questions, answers, research, assignments, documents, professional services and delivery services.' }}">
<meta property="og:url" content="{{ SITE_URL }}{{ request.path }}">
<meta name="author" content="KOJA AFRICA">
<meta name="application-name" content="KOJA AFRICA">
<meta name="theme-color" content="#0b1220">
{% if seo_jsonld %}<script type="application/ld+json">{{ seo_jsonld|safe }}</script>{% endif %}
<title>{{ title or "KOJA AFRICA" }}</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.css">
<script>
(function(){try{var t={{ theme|tojson }};var saved=localStorage.getItem("koja_theme");if(saved==="light"||saved==="dark"||saved==="system")t=saved;document.documentElement.dataset.kojaTheme=t||"system";}catch(e){}})();
</script>
<style>
*{box-sizing:border-box}
:root{color-scheme:light;--bg:#f5f7fb;--surface:#fff;--text:#172033;--muted:#667085;--border:#e4e7ec;--nav:#10233f;--accent:#176b87;--focus:#f2b84b}
html[data-koja-theme="dark"]{color-scheme:dark;--bg:#0f1720;--surface:#17212b;--text:#edf2f7;--muted:#aab7c4;--border:#30404f;--nav:#091522;--accent:#2aa7b8;--focus:#f2c15b}
@media(prefers-color-scheme:dark){html[data-koja-theme="system"]{color-scheme:dark;--bg:#0f1720;--surface:#17212b;--text:#edf2f7;--muted:#aab7c4;--border:#30404f;--nav:#091522;--accent:#2aa7b8;--focus:#f2c15b}}
body{margin:0;font-family:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:var(--bg);color:var(--text);line-height:1.55}

nav{background:#10233f;color:#fff;padding:10px 15px;position:sticky;top:0;z-index:1000;box-shadow:0 4px 18px rgba(0,0,0,.12)}
.nav-inner{max-width:1250px;margin:auto;display:flex;align-items:center;gap:7px}
.brand{font-weight:800;font-size:19px;margin-right:auto;display:flex;align-items:center;gap:8px;letter-spacing:.2px}.brand-mark{width:32px;height:32px;border-radius:9px;display:inline-grid;place-items:center;background:linear-gradient(135deg,#19a7b8,#f2b84b);box-shadow:0 5px 18px rgba(0,0,0,.22);animation:logoFloat 4s ease-in-out infinite}.brand-mark svg{width:22px;height:22px}.brand-name{white-space:nowrap}
.menu-toggle{display:none;width:auto;margin:0;padding:8px 12px;background:rgba(255,255,255,.1);border:1px solid rgba(255,255,255,.2);color:#fff;border-radius:9px;font-weight:700;cursor:pointer}
.menu-toggle:hover{background:rgba(255,255,255,.18);transform:none}
.nav-links{display:flex;align-items:center;gap:5px;flex-wrap:wrap}
nav a{color:#fff;text-decoration:none;padding:8px 9px;border-radius:7px;transition:background .2s ease,transform .2s ease}
nav a:hover{background:rgba(255,255,255,.12);transform:translateY(-1px)}
.menu-group{position:relative}.menu-group>button{width:auto;margin:0;padding:8px 10px;background:rgba(255,255,255,.08);color:#fff;border:0;border-radius:7px;cursor:pointer;font:inherit}.menu-group>button:hover{background:rgba(255,255,255,.15);transform:none}
.dropdown{display:none;position:absolute;right:0;top:calc(100% + 7px);min-width:210px;background:var(--surface);border-radius:11px;padding:7px;box-shadow:0 12px 35px rgba(0,0,0,.2);border:1px solid #e5e7eb}
.dropdown.open{display:block;animation:menuDrop .18s ease both}.dropdown a{display:block;color:var(--text)!important;padding:10px 11px;white-space:nowrap}.dropdown a:hover{background:#eef5f8;transform:none}
@keyframes menuDrop{from{opacity:0;transform:translateY(-5px)}to{opacity:1;transform:translateY(0)}}
.container{width:min(1250px,calc(100% - 24px));margin:20px auto 50px}
.card{background:var(--surface);border-radius:13px;padding:18px;margin-bottom:16px;box-shadow:0 3px 14px rgba(0,0,0,.06);animation:fadeUp .45s ease both}.card:hover{transform:translateY(-2px);box-shadow:0 8px 24px rgba(0,0,0,.09);transition:transform .2s ease,box-shadow .2s ease}
.hero{background:linear-gradient(135deg,#10233f,#176b87);color:#fff;padding:28px 20px;border-radius:15px;margin-bottom:18px}
h1,h2,h3{margin-top:0}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:15px}
input,select,textarea,button{width:100%;padding:11px 12px;margin-top:6px;margin-bottom:12px;border-radius:8px;border:1px solid var(--border);background:var(--surface);color:var(--text);font:inherit}
textarea{min-height:120px}
button,.btn{display:inline-block;background:#176b87;color:#fff;border:0;text-decoration:none;cursor:pointer;padding:10px 14px;border-radius:8px;transition:transform .2s ease,box-shadow .2s ease,filter .2s ease}button:hover,.btn:hover{transform:translateY(-2px);box-shadow:0 7px 18px rgba(0,0,0,.12);filter:brightness(1.04)}button:active,.btn:active{transform:translateY(0)}
.btn.secondary{background:#5f6b7a}.btn.success{background:#177245}.btn.danger{background:#a62d2d}.btn.warning{background:#9b6b00}
table{width:100%;border-collapse:collapse}
th,td{border-bottom:1px solid var(--border);padding:9px;text-align:left;vertical-align:top}
.alert{padding:12px;border-radius:8px;margin-bottom:10px;background:#eaf2ff}
.stat{padding:18px;background:var(--surface);border-radius:12px;box-shadow:0 2px 10px rgba(0,0,0,.05)}
.big{font-size:28px;font-weight:800}
.small{color:var(--muted);font-size:13px}.badge{display:inline-block;padding:4px 8px;border-radius:20px;background:#e7eef5;font-size:12px}
#map{height:430px;border-radius:12px;overflow:hidden}
.map-small{height:300px!important}
.driver-card{border:2px solid #e4e7ec}
.driver-card.selected{border-color:#176b87}
.online{color:#177245;font-weight:700}
.offline{color:#a62d2d;font-weight:700}
footer{text-align:center;color:var(--muted);padding:30px}
.actions{display:flex;gap:8px;flex-wrap:wrap}.actions .btn,.actions button{width:auto}
@keyframes fadeUp{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:translateY(0)}}@keyframes logoFloat{0%,100%{transform:translateY(0) rotate(0deg)}50%{transform:translateY(-2px) rotate(1deg)}}@keyframes pulseSoft{0%,100%{box-shadow:0 0 0 0 rgba(25,167,184,.18)}50%{box-shadow:0 0 0 7px rgba(25,167,184,0)}}:focus-visible{outline:3px solid var(--focus);outline-offset:2px}.hero{animation:fadeUp .55s ease both}.stat{animation:fadeUp .5s ease both}.online{animation:pulseSoft 2.4s ease-in-out infinite}@media (prefers-reduced-motion:reduce){*,*::before,*::after{animation-duration:.01ms!important;animation-iteration-count:1!important;scroll-behavior:auto!important;transition:none!important;transform:none!important}}
@media(max-width:760px){nav{padding:9px 12px}.nav-inner{position:relative;flex-wrap:wrap}.menu-toggle{display:block}.nav-links{display:none;width:100%;flex-direction:column;align-items:stretch;gap:3px;padding-top:8px}.nav-links.open{display:flex;animation:fadeUp .2s ease both}.nav-links>a{font-size:14px;padding:11px 12px;background:rgba(255,255,255,.05)}.menu-group{width:100%}.menu-group>button{width:100%;text-align:left;padding:11px 12px}.dropdown{position:static;width:100%;box-shadow:none;margin-top:4px;background:var(--surface)}.dropdown a{font-size:14px}.container{width:min(100% - 14px,1250px)}table{display:block;overflow-x:auto}#map{height:350px}.actions .btn,.actions button{width:100%}}
@media(min-width:761px){.nav-links{display:flex!important}}
</style>
</head>
<body>
<nav aria-label="Primary navigation">
<div class="nav-inner">
<div class="brand"><span class="brand-mark" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none"><path d="M5 18V6h7.2a5.3 5.3 0 0 1 0 10.6H8.5" stroke="white" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/><path d="M8.5 9.1h3.4a1.9 1.9 0 0 1 0 3.8H8.5" stroke="white" stroke-width="2.2" stroke-linecap="round"/></svg></span><span class="brand-name">KOJA AFRICA</span></div>
<button class="menu-toggle" id="menuToggle" type="button" aria-expanded="false" aria-controls="navLinks" aria-label="Open menu">☰ Menu</button>
<div class="nav-links" id="navLinks">
<a href="{{ url_for('home') }}">Home</a>
{% if user %}
<a href="{{ url_for('dashboard') }}">Dashboard</a>
<a href="{{ url_for('services') }}">Services</a>
<a href="{{ url_for('questions') }}">Questions</a>
<a href="{{ url_for('assignments') }}">Assignments</a>
<a href="{{ url_for('research') }}">🔎 Research</a>
<a href="{{ url_for('public_feed') }}">🌍 Public</a>
<a href="{{ url_for('marketplace') }}">🛒 Marketplace</a>
<a href="{{ url_for('connect') }}">💬 Communication</a>
<a href="{{ url_for('professional_communication') }}">👩‍💼 Professional Communication</a>
<a href="{{ url_for('settings') }}">⚙️ Settings</a>
<div class="menu-group">
<button type="button" id="moreMenuButton" aria-expanded="false" aria-haspopup="true">More ▾</button>
<div class="dropdown" id="moreMenu" role="menu">
<a role="menuitem" href="{{ url_for('deliveries') }}">Deliveries</a>
<a role="menuitem" href="{{ url_for('drivers') }}">Drivers</a>
{% if user.role in ['driver','admin'] or user.is_admin %}<a role="menuitem" href="{{ url_for('driver_dashboard') }}">Driver Dashboard</a>{% endif %}
{% if user and user.is_admin %}<a role="menuitem" href="{{ url_for('admin') }}">Admin</a><a role="menuitem" href="{{ url_for('admin_marketplace') }}">Marketplace Admin</a>{% endif %}
<a role="menuitem" href="{{ url_for('logout') }}">Logout</a>
</div></div>
{% else %}
<a href="{{ url_for('login') }}">Login</a>
<a href="{{ url_for('register') }}">Register</a>
{% endif %}
</div>
</div>
</nav>
<script>
(function(){
 const toggle=document.getElementById('menuToggle'), links=document.getElementById('navLinks'), more=document.getElementById('moreMenuButton'), drop=document.getElementById('moreMenu');
 if(toggle){toggle.addEventListener('click',function(){const open=links.classList.toggle('open');toggle.setAttribute('aria-expanded',open);toggle.setAttribute('aria-label',open?'Close menu':'Open menu');toggle.innerHTML=open?'✕ Close':'☰ Menu';});}
 if(more&&drop){more.addEventListener('click',function(e){e.stopPropagation();const open=drop.classList.toggle('open');more.setAttribute('aria-expanded',open);});document.addEventListener('click',function(e){if(!e.target.closest('.menu-group')){drop.classList.remove('open');more.setAttribute('aria-expanded','false');}});}
 document.querySelectorAll('#navLinks a').forEach(function(a){a.addEventListener('click',function(){if(window.innerWidth<=760&&links.classList.contains('open')){links.classList.remove('open');toggle.setAttribute('aria-expanded','false');toggle.setAttribute('aria-label','Open menu');toggle.innerHTML='☰ Menu';}});});
 window.addEventListener('resize',function(){if(window.innerWidth>760){links.classList.remove('open');toggle&&toggle.setAttribute('aria-expanded','false');toggle&&(toggle.innerHTML='☰ Menu');}});
})();
</script>
<div class="container">
{% with messages=get_flashed_messages(with_categories=true) %}
{% for category,message in messages %}<div class="alert">{{ message }}</div>{% endfor %}
{% endwith %}
{{ body|safe }}
</div>
<footer>KOJA AFRICA — Knowledge • Questions • Answers<br>Academic • Professional • Research • Communication • Health • Transport Services</footer>
<script src="https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.js"></script>
</body>
</html>
"""

def render_page(title, body_template, **context):
    context["user"] = current_user()
    body = render_template_string(body_template, **context)
    prefs = session.get("koja_settings", {}) or {}
    theme = prefs.get("theme", "system") if prefs.get("theme") in ("system", "light", "dark") else "system"
    descriptions = {
        "KOJA AFRICA": "KOJA AFRICA — knowledge, questions, answers, research, assignments, documents, professional services and delivery services.",
        "Research": "KOJA AFRICA Research Engine — search web information, scholarly literature and KOJA documents and create structured research notes and citations.",
        "Assignments": "KOJA AFRICA assignments — ask questions, upload assignments and access academic resources.",
        "Documents": "KOJA AFRICA documents and research resources for learning and academic work.",
        "Marketplace": "KOJA AFRICA Digital Marketplace — discover and sell ebooks, courses, templates, research resources, software, graphics and other digital products.",
    }
    # Google-friendly structured data for public pages. This improves entity/page
    # understanding and can enable eligible search enhancements; it does not
    # guarantee a rich result. Private/account pages intentionally get no JSON-LD.
    public_paths = {"/", "/research", "/research/notes", "/marketplace"}
    seo_jsonld = ""
    if request.path in public_paths:
        page_title = title or "KOJA AFRICA"
        page_description = descriptions.get(title, "KOJA AFRICA — knowledge, questions, answers, research, academic resources, professional services and delivery services.")
        graph = [
            {
                "@type": "Organization",
                "@id": SITE_URL + "#organization",
                "name": "KOJA AFRICA",
                "url": SITE_URL,
                "description": "Knowledge, research, academic resources, professional services and delivery services."
            },
            {
                "@type": "WebPage",
                "@id": SITE_URL + request.path + "#webpage",
                "url": SITE_URL + request.path,
                "name": page_title,
                "description": page_description,
                "isPartOf": {"@id": SITE_URL + "#website"},
                "about": {"@id": SITE_URL + "#organization"}
            },
            {
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "KOJA AFRICA", "item": SITE_URL},
                    *([] if request.path == "/" else [{"@type": "ListItem", "position": 2, "name": "Research", "item": SITE_URL + "/research"}] if request.path == "/research" else [{"@type": "ListItem", "position": 2, "name": "Research", "item": SITE_URL + "/research"}, {"@type": "ListItem", "position": 3, "name": "Research Notes", "item": SITE_URL + "/research/notes"}])
                ]
            }
        ]
        website = {
            "@type": "WebSite",
            "@id": SITE_URL + "#website",
            "name": "KOJA AFRICA",
            "url": SITE_URL,
            "publisher": {"@id": SITE_URL + "#organization"}
        }
        if request.path in ("/research", "/research/notes"):
            website["potentialAction"] = {
                "@type": "SearchAction",
                "target": SITE_URL + "/research?q={search_term_string}",
                "query-input": "required name=search_term_string"
            }
        graph.insert(0, website)
        seo_jsonld = json.dumps({"@context": "https://schema.org", "@graph": graph}, ensure_ascii=False)

    return render_template_string(BASE_HTML, title=title, body=body, user=current_user(), theme=theme, meta_description=descriptions.get(title, "KOJA AFRICA — knowledge, questions, answers, research, academic resources, professional services and delivery services."), seo_jsonld=seo_jsonld)

# ============================================================
# USER SETTINGS
# ============================================================

@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    user = current_user() or {}
    if request.method == 'POST':
        action = clean(request.form.get('action', 'preferences'))
        if action == 'preferences':
            theme = clean(request.form.get('theme', 'system')).lower()
            if theme not in ('system', 'light', 'dark'):
                theme = 'system'
            research = bool(request.form.get('allow_research'))
            session['koja_settings'] = {'theme': theme, 'allow_research': research}
            session.modified = True
            flash('Settings saved successfully.', 'success')
            return redirect(url_for('settings'))
        flash('Unknown settings action.', 'danger')
        return redirect(url_for('settings'))
    prefs = session.get('koja_settings', {'theme': 'system', 'allow_research': True})
    return render_page('Settings', r'''<div class="hero"><h2>⚙️ KOJA Settings</h2><p>Manage your KOJA appearance, research access and account preferences.</p></div>
<div class="grid">
<div class="card"><h3>Account</h3><p><strong>Name:</strong> {{ user.name or "KOJA User" }}</p><p><strong>Email:</strong> {{ user.email or "Not provided" }}</p><p><strong>Role:</strong> {{ user.role or "student" }}</p></div>
<div class="card"><h3>Appearance & Research</h3><form method="post"><input type="hidden" name="action" value="preferences"><label>Theme</label><select name="theme"><option value="system" {% if prefs.theme == 'system' %}selected{% endif %}>System</option><option value="light" {% if prefs.theme == 'light' %}selected{% endif %}>Light</option><option value="dark" {% if prefs.theme == 'dark' %}selected{% endif %}>Dark</option></select><label style="display:block;margin-top:12px"><input type="checkbox" name="allow_research" value="1" style="width:auto" {% if prefs.allow_research %}checked{% endif %}> Allow external research sources</label><button class="btn" type="submit">Save Settings</button></form></div>
<div class="card"><h3>Research</h3><p>Search scholarly literature, web sources, Wikipedia and KOJA documents, then create structured research notes and references.</p><a class="btn" href="{{ url_for('research') }}">🔎 Open Research Engine</a></div>
<div class="card"><h3>Security</h3><p>Use the Logout button to end the current session.</p><a class="btn secondary" href="{{ url_for('logout') }}">Log Out</a></div>
</div><script>localStorage.setItem('koja_theme', {{ prefs.theme|tojson }}); document.documentElement.dataset.kojaTheme={{ prefs.theme|tojson }};</script>''', prefs=prefs)

# ============================================================
# HOME / HEALTH
# ============================================================

@app.route("/")
def home():
    return render_page("KOJA AFRICA", r"""
<div class="hero">
<h1>KOJA AFRICA</h1>
<p>Knowledge • Questions • Answers</p>
<p>Research, academic questions, assignments, professional services, documents and delivery services.</p>
{% if not user %}
<div class="actions">
<a class="btn" href="{{ url_for('register') }}">Create Account</a>
<a class="btn secondary" href="{{ url_for('login') }}">Login</a>
</div>
{% endif %}
</div>
<div class="grid">
<div class="card"><h3>Academic</h3><p>Questions, assignments and learning resources.</p><a class="btn" href="{{ url_for('questions') }}">Questions</a></div>
<div class="card"><h3>CV</h3><p>Create a professional CV.</p><a class="btn" href="{{ url_for('cv') }}">Create CV</a></div>
<div class="card"><h3>Doctors</h3><p>Find a doctor and request an appointment.</p><a class="btn" href="{{ url_for('doctors') }}">Doctors</a></div>
<div class="card"><h3>Teachers</h3><p>Find teachers/tutors by subject and grade.</p><a class="btn" href="{{ url_for('teachers') }}">Teachers</a></div>
<div class="card"><h3>Deliveries</h3><p>Find nearby drivers and send delivery requests.</p><a class="btn" href="{{ url_for('deliveries') }}">Delivery</a></div>
<div class="card"><h3>Live GPS</h3><p>Drivers can share their live location.</p><a class="btn" href="{{ url_for('tracking') }}">Driver GPS</a></div>
</div>
""")

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
        if _rate_limited("register:" + (request.remote_addr or "unknown"), 8, 600):
            return "Too many registration attempts. Please wait and try again.", 429
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
        # Do not attempt to write to any legacy/nonexistent table after a
        # profiles insert failure. The current KOJA schema stores accounts in
        # public.profiles; the original database error must be preserved so it
        # can be diagnosed correctly.
        if error:
            logger.error("Registration failed: %s", error)
            flash(f"Registration failed: {str(error)[:500]}","danger")
            return redirect(url_for("register"))

        login_user(row or payload)
        log_activity("registration","New KOJA account registered.")
        flash("Account created successfully.","success")
        return redirect(url_for("dashboard"))

    return render_page("Register", r"""
<div class="card" style="max-width:600px;margin:auto">
<h2>Create KOJA Account</h2>
<form method="post">
<label>Full Name</label><input name="full_name" required>
<label>Email</label><input name="email" type="email" required>
<label>Phone</label><input name="phone">
<label>Account Type</label>
<select name="role">
<option value="student">Student / Customer</option>
<option value="driver">Delivery Driver</option>
<option value="teacher">Teacher / Tutor</option>
<option value="doctor">Doctor</option>
</select>
<label>Password</label><input name="password" type="password" minlength="6" required>
<button type="submit">Create Account</button>
</form>
<p>Already registered? <a href="{{ url_for('login') }}">Login</a></p>
</div>
""")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        if _rate_limited("login:" + (request.remote_addr or "unknown"), 12, 300):
            return "Too many login attempts. Please wait a few minutes and try again.", 429
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

    return render_page("Login", r"""
<div class="card" style="max-width:500px;margin:auto">
<h2>KOJA Login</h2>
<p class="small">KOJA supports its local profile password and, when configured, Supabase Auth accounts.</p>
<form method="post">
<label>Email</label><input name="email" type="email" autocomplete="email" required>
<label>Password</label><input name="password" type="password" autocomplete="current-password" required>
<button type="submit">Login</button>
</form>
<p>No account? <a href="{{ url_for('register') }}">Create one</a></p>
</div>
""")

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
    return render_page("Dashboard", r"""
<div class="hero"><h2>Welcome, {{ user.name }}</h2><p>{{ user.email }}</p></div>
<div class="grid">
<div class="stat"><div class="big">{{ questions_count }}</div>Academic Questions</div>
<div class="stat"><div class="big">{{ deliveries_count }}</div>Deliveries</div>
<div class="stat"><div class="big">{{ appointments_count }}</div>Appointments</div>
<div class="stat"><div class="big">{{ "ADMIN" if user.is_admin else user.role|upper }}</div>Account</div>
</div>
<div class="card"><h3>KOJA Services</h3>
<div class="grid">
<a class="btn" href="{{ url_for('cv') }}">Create CV</a>
<a class="btn" href="{{ url_for('doctors') }}">Doctor Booking</a>
<a class="btn" href="{{ url_for('teachers') }}">Teacher Booking</a>
<a class="btn" href="{{ url_for('deliveries') }}">Find Driver / Delivery</a>
{% if user.role in ['driver','admin'] or user.is_admin %}<a class="btn" href="{{ url_for('driver_dashboard') }}">Driver Dashboard</a>{% endif %}
</div></div>
""",questions_count=questions_count,deliveries_count=deliveries_count,appointments_count=appointments_count)

# ============================================================
# KOJA RESEARCH ENGINE V2
# Web + Academic + KOJA Documents + filters + AI-assisted summaries
# ============================================================

def _research_year(value):
    try:
        y=int(value)
        return y if 1000 <= y <= 2100 else None
    except Exception:
        return None

def research_web(query, limit=8):
    q=clean(query)
    if not q: return []
    out=[]
    try:
        r=requests.get('https://api.duckduckgo.com/',params={'q':q,'format':'json','no_html':1,'skip_disambig':1},timeout=10,headers={'User-Agent':'KOJA-AFRICA-Research/2.0'})
        if r.ok:
            d=r.json()
            if d.get('AbstractText'):
                out.append({'source':'Web','title':d.get('Heading') or q,'url':d.get('AbstractURL') or 'https://duckduckgo.com/?q='+quote(q),'snippet':d.get('AbstractText'),'year':None})
            for item in d.get('RelatedTopics',[]):
                if item.get('FirstURL') and item.get('Text'):
                    out.append({'source':'Web','title':item.get('Text'),'url':item.get('FirstURL'),'snippet':item.get('Text'),'year':None})
    except Exception as exc: logger.warning('Web research failed: %s',exc)
    return out[:limit]

def research_wikipedia(query, limit=6):
    q=clean(query)
    if not q: return []
    try:
        r=requests.get('https://en.wikipedia.org/w/api.php',params={'action':'query','list':'search','srsearch':q,'srlimit':limit,'format':'json','utf8':1},timeout=10,headers={'User-Agent':'KOJA-AFRICA-Research/2.0'})
        if not r.ok: return []
        out=[]
        for x in r.json().get('query',{}).get('search',[]):
            title=clean(x.get('title',''))
            if title:
                snippet=clean(x.get('snippet','')).replace('<span class="searchmatch">','').replace('</span>','')
                out.append({'source':'Wikipedia','title':title,'url':'https://en.wikipedia.org/wiki/'+quote(title.replace(' ','_')),'snippet':snippet,'year':None})
        return out
    except Exception as exc: logger.warning('Wikipedia research failed: %s',exc); return []

def research_openalex(query, year=None, limit=10):
    q=clean(query)
    if not q: return []
    try:
        params={'search':q,'per-page':limit,'mailto':os.getenv('RESEARCH_EMAIL','').strip()}
        if year: params['filter']=f'publication_year:{year}'
        params={k:v for k,v in params.items() if v}
        r=requests.get('https://api.openalex.org/works',params=params,timeout=12,headers={'User-Agent':'KOJA-AFRICA-Research/6.0'})
        if not r.ok: return []
        out=[]
        for x in r.json().get('results',[]):
            title=clean(x.get('display_name') or '')
            if not title: continue
            authors=[clean((a.get('author') or {}).get('display_name','')) for a in (x.get('authorships') or [])]
            authors=[a for a in authors if a]
            inv=x.get('abstract_inverted_index') or {}; words=[]
            for word,positions in inv.items():
                for pos in positions: words.append((pos,word))
            abstract=' '.join(w for _,w in sorted(words))
            loc=x.get('primary_location') or {}; source_obj=loc.get('source') or {}
            journal=clean(source_obj.get('display_name') or '')
            doi=clean(x.get('doi') or '')
            url=doi or loc.get('landing_page_url') or x.get('id') or ''
            cited=x.get('cited_by_count') or 0; yr=x.get('publication_year')
            out.append({'source':'OpenAlex','title':title,'url':url,'snippet':abstract[:1200],'year':yr,'citations':cited,'authors':authors,'journal':journal,'doi':doi,'source_type':'journal_article' if journal else 'other','_concepts':[clean(c.get('display_name','')) for c in (x.get('concepts') or []) if clean(c.get('display_name',''))]})
        return out
    except Exception as exc: logger.warning('OpenAlex research failed: %s',exc); return []

def research_crossref(query, year=None, author=None, limit=10):
    q=clean(query)
    if not q: return []
    try:
        params={'query.bibliographic':q,'rows':limit,'select':'title,author,published,URL,DOI,container-title,type,is-referenced-by-count,publisher,volume,issue,page,edition'}
        if year: params['filter']=f'from-pub-date:{year}-01-01,until-pub-date:{year}-12-31'
        if author: params['query.author']=clean(author)
        mail=os.getenv('RESEARCH_EMAIL','').strip()
        if mail: params['mailto']=mail
        r=requests.get('https://api.crossref.org/works',params=params,timeout=12,headers={'User-Agent':'KOJA-AFRICA-Research/6.0'})
        if not r.ok: return []
        out=[]
        for x in r.json().get('message',{}).get('items',[]):
            title=clean((x.get('title') or [''])[0])
            if not title: continue
            authors=[clean(' '.join(filter(None,[a.get('given'),a.get('family')]))) for a in (x.get('author') or [])]
            authors=[a for a in authors if a]
            parts=(x.get('published') or {}).get('date-parts') or []; yr=parts[0][0] if parts and parts[0] else None
            doi=clean(x.get('DOI') or ''); url=x.get('URL') or (('https://doi.org/'+doi) if doi else '')
            journal=clean((x.get('container-title') or [''])[0]); typ=clean(x.get('type') or '')
            st='journal_article' if typ in ('journal-article','proceedings-article') or journal else ('book' if 'book' in typ else 'other')
            out.append({'source':'Crossref','title':title,'url':url,'snippet':' • '.join([p for p in [journal,str(yr) if yr else '',f"Citations: {x.get('is-referenced-by-count') or 0}" if x.get('is-referenced-by-count') else ''] if p]),'year':yr,'citations':x.get('is-referenced-by-count') or 0,'authors':authors,'journal':journal,'doi':doi,'publisher':clean(x.get('publisher') or ''),'volume':clean(x.get('volume') or ''),'issue':clean(x.get('issue') or ''),'pages':clean(x.get('page') or ''),'edition':clean(x.get('edition') or ''),'source_type':st})
        return out
    except Exception as exc: logger.warning('Crossref research failed: %s',exc); return []

def research_local_documents(query, limit=12):
    q=clean(query).lower()
    if not q: return []
    terms=[t for t in q.split() if len(t)>1][:12]; rows=[]
    for table in ('documents','document_records'):
        try:
            for row in db_select(table,limit=500):
                blob=' '.join(str(row.get(k,'')) for k in row.keys() if k!='id').strip(); low=blob.lower()
                score=sum(low.count(t) for t in terms)
                if score<=0: continue
                title=clean(row.get('title') or row.get('name') or row.get('document_name') or row.get('filename') or 'KOJA Document')
                desc=clean(row.get('description') or row.get('content') or row.get('text') or row.get('details') or '')
                url=row.get('url') or row.get('public_url') or row.get('file_url') or row.get('download_url') or ''
                rows.append({'source':'KOJA Documents','title':title,'url':url,'snippet':desc[:900] or blob[:900],'year':_research_year(row.get('year') or row.get('publication_year')),'_score':score})
        except Exception as exc: logger.info('Document search skipped for %s: %s',table,exc)
    rows.sort(key=lambda x:(x.get('_score',0),x.get('year') or 0),reverse=True)
    for r in rows: r.pop('_score',None)
    return rows[:limit]

def _research_tokens(q):
    return [t for t in re.findall(r"[\w\'-]+", clean(q).lower()) if len(t)>1]

def _research_score(r, query):
    q=clean(query).lower(); toks=_research_tokens(query)
    title=clean(r.get('title','')).lower(); snippet=clean(r.get('snippet','')).lower()
    authors=' '.join(_names(r)).lower(); journal=clean(r.get('journal','')).lower()
    if not toks: return 0
    score=0
    if title==q: score+=100
    if q and q in title: score+=60
    for t in toks:
        if t in title: score+=18
        if t in authors: score+=12
        if t in journal: score+=5
        if t in snippet: score+=2
    if str(r.get('source','')).lower() in ('openalex','crossref'): score+=8
    if r.get('doi'): score+=4
    score+=min(int(r.get('citations') or 0),100)/20
    r['_relevance']=round(score,2); return r['_relevance']

def _research_key(r):
    doi=clean(r.get('doi') or '').lower().replace('https://doi.org/','').strip()
    if doi: return 'doi:'+doi
    u=clean(r.get('url') or '').lower().rstrip('/')
    if u: return 'url:'+u
    title=re.sub(r'[^a-z0-9]+',' ',clean(r.get('title','')).lower()).strip()
    return 'title:'+title

def _research_deduplicate(results, query):
    merged={}
    for r in results:
        _research_score(r,query); k=_research_key(r)
        if k not in merged: merged[k]=dict(r); continue
        old=merged[k]
        if len(clean(r.get('snippet',''))) > len(clean(old.get('snippet',''))): old['snippet']=r.get('snippet','')
        for fld in ('authors','journal','doi','publisher','volume','issue','pages','edition','year','citations','source_type'):
            if not old.get(fld) and r.get(fld): old[fld]=r.get(fld)
        sources=set(str(old.get('source','')).split(' + ')); sources.add(str(r.get('source',''))); old['source']=' + '.join(sorted(x for x in sources if x))
        old['_relevance']=max(old.get('_relevance',0),r.get('_relevance',0))
    return sorted(merged.values(),key=lambda r:(r.get('_relevance',0),r.get('citations') or 0,r.get('year') or 0),reverse=True)

def _research_filter(results, source='all', year=None, sort='relevance'):
    source=(source or 'all').lower(); source=source if source in ('all','web','wikipedia','academic','koja') else 'all'
    if source!='all':
        if source=='academic': results=[r for r in results if any(x in str(r.get('source','')).lower() for x in ('openalex','crossref'))]
        elif source=='koja': results=[r for r in results if 'koja documents' in str(r.get('source','')).lower()]
        else: results=[r for r in results if str(r.get('source','')).lower()==source]
    if year: results=[r for r in results if str(r.get('year') or '')==str(year)]
    if sort=='date': results.sort(key=lambda r:r.get('year') or 0,reverse=True)
    elif sort=='citations': results.sort(key=lambda r:r.get('citations') or 0,reverse=True)
    else: results.sort(key=lambda r:r.get('_relevance',0),reverse=True)
    return results

def _openai_text(prompt, system_prompt, max_output_tokens=900, timeout=40):
    api_key=os.getenv("AI_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        return ""
    endpoint=os.getenv("AI_API_URL","https://api.openai.com/v1/responses")
    model=os.getenv("AI_MODEL","gpt-5.6-luna")
    payload={"model":model,"input":[{"role":"system","content":[{"type":"input_text","text":system_prompt}]},{"role":"user","content":[{"type":"input_text","text":prompt}]}],"max_output_tokens":max_output_tokens}
    try:
        r=requests.post(endpoint,json=payload,timeout=timeout,headers={"Authorization":"Bearer "+api_key,"Content-Type":"application/json"})
        if not r.ok:
            logger.warning("OpenAI request failed: %s", r.text[:500])
            return ""
        data=r.json()
        text=clean(data.get("output_text") or "")
        if text: return text
        parts=[]
        for item in data.get("output") or []:
            for content in item.get("content") or []:
                if content.get("type") in ("output_text","text") and content.get("text"):
                    parts.append(content["text"])
        return clean("\n".join(parts))
    except Exception as exc:
        logger.warning("OpenAI request failed: %s", exc)
        return ""

def research_ai_summary(query, results):
    if not results: return ''
    source_text='\n\n'.join(f"[{i+1}] {r.get('title','')} ({r.get('source','')})\n{r.get('snippet','')[:1200]}" for i,r in enumerate(results[:10]))
    text=_openai_text(
        f"Question: {query}\n\nSources:\n{source_text}\n\nWrite a concise research summary with 3-5 key findings and a short evidence note.",
        'You are KOJA Research. Summarize only the supplied sources. Do not invent facts. Cite source numbers like [1] [2]. State when evidence is limited.',
        700, 30
    )
    if text: return text
    highlights=[]
    for r in results[:5]:
        ss=clean(r.get('snippet','')).replace('\n',' ')
        if ss: highlights.append(f"{r.get('title','Source')}: {ss[:300]}")
    return 'AI summary is not configured. Source-based highlights:\n\n'+'\n\n'.join(highlights)


# KOJA V4 citation engine: source-type-aware bibliography fields
CITATION_STYLES={"apa":"APA 7th edition","mla":"MLA 9th edition","chicago":"Chicago Author–Date","harvard":"Harvard","vancouver":"Vancouver","ieee":"IEEE","ama":"AMA","oscola":"OSCOLA"}
SOURCE_TYPES={"journal_article":"Journal article","book":"Book","book_chapter":"Book chapter","website":"Website","government_report":"Government report","thesis":"Thesis / dissertation","conference_paper":"Conference paper","newspaper":"Newspaper article","dataset":"Dataset","legislation":"Legislation","court_case":"Court case","other":"Other"}
def _source_type(r):
    st=str(r.get("source_type") or "").lower().replace("-","_").replace(" ","_")
    if st in SOURCE_TYPES:return st
    if r.get("journal"):return "journal_article"
    if str(r.get("source","")).lower() in ("web","wikipedia"):return "website"
    return "other"
def _names(r):
    a=r.get("authors") or []
    if isinstance(a,str):a=[x.strip() for x in a.split(",") if x.strip()]
    return [clean(str(x)) for x in a if clean(str(x))]
def _apa(n):
    p=n.split(); return (p[-1]+", "+" ".join(x[0]+"." for x in p[:-1])).strip() if len(p)>1 else n
def make_reference(r,style="apa",n=1):
    a=_names(r); auth=", ".join(_apa(x) for x in a) or "KOJA AFRICA"; title=clean(r.get("title") or "Untitled"); year=r.get("year") or "n.d."; journal=clean(r.get("journal") or ""); doi=clean(r.get("doi") or ""); url=clean(r.get("url") or ""); publisher=clean(r.get("publisher") or ""); st=_source_type(r)
    if style=="apa":
        if st=="journal_article": return f"{auth} ({year}). {title}. {journal}."+(f" https://doi.org/{doi.replace('https://doi.org/','')}" if doi else (f" {url}" if url else ""))
        if st=="book": return f"{auth} ({year}). <i>{title}</i>. {publisher}."
        return f"{auth} ({year}). {title}. {publisher or journal or 'Website'}. {url}".strip()
    if style=="mla": return f'{auth}. "{title}." {journal or publisher}, {year}. {url}'.strip()
    if style=="chicago": return f'{auth}. {year}. "{title}." {journal or publisher}. {url}'.strip()
    if style=="harvard": return f"{auth} ({year}) {title}. {journal or publisher or 'Website'}. Available at: {url}."
    if style in ("vancouver","ama"): return f"{n}. {auth}. {title}. {journal or publisher or 'Website'}. {year}."+(f" doi:{doi.replace('https://doi.org/','')}" if doi else "")
    if style=="ieee": return f'[{n}] {auth}, "{title}," {journal or publisher}, {year}.'+(f" doi: {doi.replace('https://doi.org/','')}" if doi else (f" [Online]. Available: {url}" if url else ""))
    return f'{auth}, "{title}" ({year}) {journal or publisher or url}'
def make_intext(r,style,n):
    a=_names(r); short=a[0].split()[-1] if a else "KOJA AFRICA"; y=r.get("year") or "n.d."
    if style in ("vancouver","ama","ieee"):return f"[{n}]"
    if style=="mla":return f"({short} {y})"
    return f"({short}{' et al.' if len(a)>2 else ''}, {y})"
def make_bibliography(results,style): return [(i+1,make_reference(r,style,i+1)) for i,r in enumerate(results)]
def research_ai_notes(query, results, style='apa'):
    if not results: return 'No sufficiently relevant evidence was retrieved for this topic.'
    bundle=[]
    for i,r in enumerate(results[:12],1):
        bundle.append(f"[{i}] {r.get('title','')} | {r.get('source','')} | {r.get('year') or 'n.d.'}\nAuthors: {', '.join(_names(r))}\nEvidence: {clean(r.get('snippet',''))[:1600]}\nURL: {r.get('url','')}")
    prompt=(f'Write high-quality research notes on: {query}\n\nUse ONLY the evidence supplied below. Do not invent facts, figures, quotations, authors, dates, references or conclusions. Every substantive factual claim must have one or more source-number citations such as [1] immediately after the claim. If evidence is insufficient, say so.\n\nStructure the notes with: Title; Introduction; Key concepts/background; Main findings/themes; Evidence and discussion; Implications; Conclusion; Research gaps/limitations only if supported. Write connected explanatory paragraphs, like strong academic study notes, not disconnected bullet fragments. Use the selected citation style for the reference list: {CITATION_STYLES.get(style,style)}.\n\nSOURCES:\n' + '\n\n'.join(bundle))
    text=_openai_text(prompt,'You are KOJA Research Notes. Be evidence-bound, clear, academic and concise. Never fabricate citations or source details.',2200,45)
    if text: return text
    lines=[f"# Research Notes: {query}","","## Introduction",f"The search retrieved {len(results)} relevant records. The notes below are limited to the evidence contained in those records.",""]
    for i,r in enumerate(results[:8],1):
        evidence=clean(r.get('snippet',''))
        if evidence: lines += [f"## {i}. {r.get('title','Untitled')} [{i}]",evidence,""]
    lines += ["## Conclusion","The available evidence is source-dependent and should be checked against the original publications before formal submission."]
    return '\n'.join(lines)


@app.route('/research/notes')
def research_notes():
    q=clean(request.args.get('q','')); style=clean(request.args.get('style','apa')).lower() or 'apa'
    if style not in CITATION_STYLES: style='apa'
    results=[]
    if q:
        raw=research_web(q,6)+research_wikipedia(q,5)+research_openalex(q,None,10)+research_crossref(q,None,None,10)+research_local_documents(q,10)
        results=_research_deduplicate(raw,q)[:12]
    notes=research_ai_notes(q,results,style) if q else ''
    bibliography=make_bibliography(results,style) if results else []
    return render_page('Research Notes', r'''<style>
.notes-shell{max-width:1000px;margin:auto}.notes-toolbar{display:grid;grid-template-columns:1fr auto auto;gap:10px}.notes-body{line-height:1.8;font-size:1rem}.notes-body pre{white-space:pre-wrap;font:inherit}.ref{margin:10px 0}.note-actions{display:flex;gap:8px;flex-wrap:wrap;margin:12px 0}@media(max-width:700px){.notes-toolbar{grid-template-columns:1fr}.notes-body{font-size:.97rem}}
</style><div class="notes-shell"><div class="hero"><h2>📝 KOJA Research Notes</h2><p>Turn ranked research evidence into clear, connected academic notes.</p><form method="get" action="{{ url_for('research_notes') }}" class="notes-toolbar"><input name="q" value="{{ q }}" placeholder="Enter your research topic…" required><select name="style">{% for k,v in citation_styles.items() %}<option value="{{k}}" {% if style==k %}selected{% endif %}>{{v}}</option>{% endfor %}</select><button class="btn">Write Notes</button></form></div>{% if q %}<div class="note-actions"><button class="btn secondary" type="button" onclick="copyKOJANotes()">Copy Notes</button><button class="btn secondary" type="button" onclick="window.print()">Print</button><a class="btn secondary" href="{{ url_for('research',q=q,style=style) }}">View Evidence</a></div><div class="card"><strong>{{ results|length }} ranked evidence sources</strong></div><div id="koja-notes" class="card notes-body"><pre>{{ notes }}</pre></div>{% if bibliography %}<div class="card"><h3>References</h3>{% for n,ref in bibliography %}<div class="ref">{{ n }}. {{ ref|safe }}</div>{% endfor %}</div>{% endif %}<script>function copyKOJANotes(){const el=document.getElementById('koja-notes');navigator.clipboard.writeText(el.innerText).then(()=>alert('Research notes copied.')).catch(()=>alert('Select and copy the notes manually.'))}</script>{% else %}<div class="card"><h3>How KOJA writes notes</h3><p>1. Searches multiple evidence sources.</p><p>2. Removes duplicates and ranks relevance.</p><p>3. Gives the AI only the strongest evidence.</p><p>4. Produces connected academic paragraphs with source citations.</p><p>5. Generates a bibliography in your selected citation style.</p></div>{% endif %}</div>''',q=q,style=style,citation_styles=CITATION_STYLES,results=results,notes=notes,bibliography=bibliography)

@app.route('/research')
def research():
    q=clean(request.args.get('q','')); source_filter=clean(request.args.get('source','all')).lower() or 'all'; sort=clean(request.args.get('sort','relevance')).lower() or 'relevance'; year=_research_year(request.args.get('year','')); author=clean(request.args.get('author','')); style=clean(request.args.get('style','apa')).lower() or 'apa'; source_type=clean(request.args.get('source_type','all')).lower() or 'all'
    if style not in CITATION_STYLES: style='apa'
    results=[]
    if q:
        results += research_web(q,8)+research_wikipedia(q,6)+research_openalex(q,year,10)+research_crossref(q,year,author,10)+research_local_documents(q,12)
        results=_research_deduplicate(results,q)
        results=_research_filter(results,source_filter,year,sort)
        if source_type!='all': results=[r for r in results if _source_type(r)==source_type]
    summary=research_ai_summary(q,results) if q else ''
    bibliography=make_bibliography(results,style) if results else []
    return render_page('Research', r'''
<style>
.research-shell{max-width:1100px;margin:auto}.research-search{display:grid;grid-template-columns:1fr auto;gap:10px}.research-search input{min-width:0}.research-filters{display:grid;grid-template-columns:1fr 1fr 1fr 1fr;gap:10px;margin-top:12px}.research-filters label{font-size:.82rem;font-weight:700}.research-filters select,.research-filters input{width:100%;margin-top:5px}.research-tabs{display:flex;gap:8px;overflow:auto;margin:14px 0}.research-tabs a{white-space:nowrap}.source-badge{display:inline-block;padding:5px 9px;border-radius:999px;background:rgba(80,150,255,.14);font-size:.78rem;font-weight:800}.research-result h3{line-height:1.35}.research-meta{font-size:.82rem;opacity:.8}.research-summary{border-left:4px solid #62a8ff}.research-summary pre{white-space:pre-wrap;font:inherit;line-height:1.6}.research-count{font-weight:700}.research-empty{padding:28px;text-align:center}@media(max-width:700px){.research-search{grid-template-columns:1fr}.research-filters{grid-template-columns:1fr 1fr}.research-result{padding:16px!important}}
</style>
<div class="research-shell"><div class="hero"><h2>🔎 KOJA Research Engine</h2><p>Search the web, scholarly literature and your KOJA document collection from one research workspace.</p><form method="get" action="{{ url_for('research') }}" class="research-search" style="margin-top:18px"><input name="q" value="{{ q }}" placeholder="Ask a question, topic, paper, author or subject…" aria-label="Research search"><button class="btn" type="submit">Search</button></form>
<div class="research-filters"><label>Source<select name="source" form="research-filter-form"><option value="all" {% if source_filter=='all' %}selected{% endif %}>All sources</option><option value="academic" {% if source_filter=='academic' %}selected{% endif %}>Academic</option><option value="web" {% if source_filter=='web' %}selected{% endif %}>Web</option><option value="wikipedia" {% if source_filter=='wikipedia' %}selected{% endif %}>Wikipedia</option><option value="koja" {% if source_filter=='koja' %}selected{% endif %}>KOJA Documents</option></select></label><label>Year<input name="year" form="research-filter-form" value="{{ year or '' }}" placeholder="e.g. 2025" inputmode="numeric"></label><label>Author<input name="author" form="research-filter-form" value="{{ author }}" placeholder="Academic author"></label><label>Citation style<select name="style" form="research-filter-form">{% for k,v in citation_styles.items() %}<option value="{{k}}" {% if style==k %}selected{% endif %}>{{v}}</option>{% endfor %}</select></label><label>Source type<select name="source_type" form="research-filter-form"><option value="all">All source types</option>{% for k,v in source_types.items() %}<option value="{{k}}" {% if source_type==k %}selected{% endif %}>{{v}}</option>{% endfor %}</select></label><label>Sort<select name="sort" form="research-filter-form"><option value="relevance" {% if sort=='relevance' %}selected{% endif %}>Relevance</option><option value="date" {% if sort=='date' %}selected{% endif %}>Newest first</option><option value="citations" {% if sort=='citations' %}selected{% endif %}>Most cited</option></select></label></div><form id="research-filter-form" method="get" action="{{ url_for('research') }}"><input type="hidden" name="q" value="{{ q }}"></form></div>
{% if q %}<div class="note-actions"><a class="btn" href="{{ url_for('research_notes',q=q,style=style) }}">📝 Write Research Notes from this topic</a></div><div class="research-tabs"><a class="btn secondary" href="{{ url_for('research',q=q,source='all',sort=sort,year=year,author=author) }}">All</a><a class="btn secondary" href="{{ url_for('research',q=q,source='academic',sort=sort,year=year,author=author) }}">🎓 Academic</a><a class="btn secondary" href="{{ url_for('research',q=q,source='web',sort=sort,year=year,author=author) }}">🌐 Web</a><a class="btn secondary" href="{{ url_for('research',q=q,source='koja',sort=sort,year=year,author=author) }}">📁 KOJA Documents</a></div><div class="card"><span class="research-count">{{ results|length }} results</span> for <strong>“{{ q }}”</strong></div>{% if summary %}<div class="card research-summary"><h3>🧠 Research Summary</h3><pre>{{ summary }}</pre><p class="small">AI summaries use configured AI credentials when available; otherwise KOJA shows source-based highlights. Verify important claims against original sources.</p></div>{% endif %}{% for r in results %}<div class="card research-result"><span class="source-badge">{{ r.source }}</span><h3><a href="{{ r.url or '#' }}" {% if r.url %}target="_blank" rel="noopener noreferrer"{% endif %}>{{ r.title }}</a></h3>{% if r.year or r.citations %}<p class="research-meta">{% if r.year %}{{ r.year }}{% endif %}{% if r.citations %} • {{ r.citations }} citations{% endif %}</p>{% endif %}<p>{{ r.snippet }}</p><p><strong>In-text:</strong> {{ make_intext(r,style,loop.index) }}</p>{% if r.url %}<a class="btn secondary" href="{{ r.url }}" target="_blank" rel="noopener noreferrer">Open original source ↗</a>{% endif %}</div>{% else %}<div class="card research-empty"><h3>No matching results</h3><p>Try a broader question, remove the year/author filter, or search another source.</p></div>{% endfor %}{% if bibliography %}<div class="card"><h2>References</h2><p class="small">Generated from available source metadata. Verify against the original source.</p>{% for n,ref in bibliography %}<p style="padding-left:28px;text-indent:-28px;line-height:1.6">{{ ref|safe }}</p>{% endfor %}</div>{% endif %}{% else %}<div class="grid"><div class="card"><h3>🌐 Web Discovery</h3><p>Discover general web knowledge.</p></div><div class="card"><h3>🎓 Academic Search</h3><p>OpenAlex and Crossref provide scholarly metadata, authors, years and citation information.</p></div><div class="card"><h3>📁 KOJA Documents</h3><p>Search documents already connected to your KOJA Supabase database.</p></div><div class="card"><h3>🧠 AI Research Summary</h3><p>Configure an AI API key to synthesize retrieved evidence with source-number citations.</p></div></div>{% endif %}</div>
''',q=q,results=results,summary=summary,source_filter=source_filter,sort=sort,year=year,author=author,style=style,source_type=source_type,citation_styles=CITATION_STYLES,source_types=SOURCE_TYPES,bibliography=bibliography,make_intext=make_intext,SITE_URL=SITE_URL)


@app.route("/services")
@login_required
def services():
    return render_page("Services", r"""
<div class="hero"><h2>KOJA Services</h2><p>Choose a service.</p></div>
<div class="grid">
<div class="card"><h3>Academic Questions</h3><a class="btn" href="{{ url_for('questions') }}">Open</a></div>
<div class="card"><h3>Assignments</h3><a class="btn" href="{{ url_for('assignments') }}">Open</a></div>
<div class="card"><h3>CV</h3><a class="btn" href="{{ url_for('cv') }}">Open</a></div>
<div class="card"><h3>Doctors</h3><p>Find doctors, view profiles and request appointments.</p><a class="btn" href="{{ url_for('doctors') }}">Find Doctors</a><a class="btn secondary" href="{{ url_for('professional_register') }}">Register</a></div>
<div class="card"><h3>Teachers / Tutors</h3><p>Find teachers and tutors by subject, grade and qualification.</p><a class="btn" href="{{ url_for('teachers') }}">Find Tutors</a><a class="btn secondary" href="{{ url_for('professional_register') }}">Register</a></div>
<div class="card"><h3>All Professionals</h3><p>Register and find professionals in many fields including law, accounting, engineering, ICT, construction, beauty, counselling and more.</p><a class="btn" href="{{ url_for('professionals') }}">Find Professionals</a><a class="btn secondary" href="{{ url_for('professional_register') }}">Register Profession</a></div>
<div class="card"><h3>Deliveries</h3><a class="btn" href="{{ url_for('deliveries') }}">Open</a></div>
</div>
""")

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
    return render_page("Questions",r"""
<div class="card"><h2>Ask an Academic Question</h2>
<form method="post">
<label>Subject</label><input name="subject" placeholder="Mathematics, Biology, Chemistry...">
<label>Question</label><textarea name="question" required></textarea>
<button type="submit">Submit Question</button>
</form></div>
<div class="card"><h2>My Questions</h2>
{% for q in rows %}
<div class="card"><strong>{{ q.get("subject") or "Academic" }}</strong>
<p>{{ q.get("question") or q.get("question_text") }}</p>
{% if q.get("answer") %}<hr><strong>Answer</strong><p>{{ q.get("answer") }}</p>{% endif %}
<span class="badge">{{ q.get("status") or "Submitted" }}</span></div>
{% else %}<p>No questions submitted yet.</p>{% endfor %}
</div>
""",rows=rows)

def make_assignment_tracking_code():
    # Short, human-friendly code tied to the assignment owner/sender.
    return "KJA-" + secrets.token_hex(5).upper()

def assignment_owner_id(item):
    if isinstance(item, list):
        item = item[0] if item else {}
    if not isinstance(item, dict):
        return None
    return item.get("owner_id") or item.get("sender_id") or item.get("user_id") or item.get("student_id")

def can_access_assignment(item, user):
    if not item or not user:
        return False
    if user.get("is_admin"):
        return True
    return str(assignment_owner_id(item) or "") == str(user.get("id") or "")

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
            "student_id":user["id"],
            "user_id":user["id"],
            "owner_id":user["id"],
                "tracking_code":make_assignment_tracking_code(),
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
            minimal={"id":payload["id"],"title":title,"description":description,
                      "student_id":user["id"],"user_id":user["id"],
                      "owner_id":user["id"],"sender_id":user["id"],
                      "tracking_code":payload["tracking_code"]}
            if uploaded:
                minimal.update({"file_name":uploaded["file_name"],"file_path":uploaded["path"],"file_url":uploaded["url"]})
            row,error=db_insert("assignments",minimal)
        if error:
            flash("Assignment could not be saved. Check assignments table columns.","danger")
        else:
            flash("Assignment uploaded successfully.","success")
        return redirect(url_for("assignments"))

    if user.get("is_admin"):
        rows=db_select("assignments",order="created_at.desc",limit=100)
    else:
        # Assignments and their documents are private to their specific sender/owner.
        rows=db_select("assignments",filters={"owner_id":user["id"]},order="created_at.desc",limit=100)
        if not rows:
            rows=db_select("assignments",filters={"user_id":user["id"]},order="created_at.desc",limit=100)
    return render_page("Assignments",r"""
<div class="card"><h2>Upload Assignment</h2>
<p class="small">Each assignment is linked to your account as its specific sender and owner. Other users cannot see your assignment documents.</p>
<form method="post" enctype="multipart/form-data">
<label>Assignment Title</label><input name="title" required>
<label>Description / Question</label><textarea name="description"></textarea>
<label>Assignment File</label><input type="file" name="file" accept=".pdf,.doc,.docx,.txt,.jpg,.jpeg,.png">
<button type="submit">Upload Assignment</button>
</form></div>
<div class="card"><h2>{% if current_user and current_user.get("is_admin") %}All Assignments{% else %}My Assignments{% endif %}</h2>
{% for item in rows %}
<div class="card"><h3>{{ item.get("title") or "Assignment" }}</h3>
<p>{{ item.get("description") or "" }}</p>
<p class="small"><strong>Sender/Owner:</strong> {{ item.get("sender_id") or item.get("owner_id") or item.get("user_id") or item.get("student_id") }}{% if item.get("tracking_code") %} · <strong>Tracking:</strong> {{ item.get("tracking_code") }}{% endif %}</p>
<a class="btn secondary" href="{{ url_for('assignment_question_download',assignment_id=item.get('id')) }}">⬇️ Download Question</a>
<a class="btn secondary" href="{{ url_for('assignment_question_view',assignment_id=item.get('id')) }}">📖 Read Question</a>
{% if item.get("file_path") %}<a class="btn" href="{{ url_for('assignment_file',assignment_id=item.get('id'),kind='original') }}">⬇️ Download Assignment File</a>{% endif %}
{% if item.get("answer_file_path") %}<a class="btn success" href="{{ url_for('assignment_file',assignment_id=item.get('id'),kind='answer') }}">⬇️ Download Answer</a>{% endif %}
{% if item.get("answered_file_path") %}<a class="btn success" href="{{ url_for('assignment_file',assignment_id=item.get('id'),kind='answered') }}">Download Answered File</a>{% endif %}
</div>
{% else %}<p>No assignments found for this account.</p>{% endfor %}
</div>
""",rows=rows,current_user=user)

@app.route("/assignments/<assignment_id>/question", methods=["GET"])
@login_required
def assignment_question_view(assignment_id):
    item = first_row("assignments", {"id": assignment_id})
    if not item:
        return "Assignment not found.", 404
    user = current_user()
    if not can_access_assignment(item, user):
        return "You are not authorized to access this assignment question.", 403
    return render_page("Assignment Question", r"""
<div class="hero"><h2>📖 Assignment Question</h2><p>{{ item.get("title") or "Assignment" }} · {{ item.get("tracking_code") or "No tracking code" }}</p></div>
<div class="card"><p><strong>Status:</strong> <span class="badge">{{ item.get("status") or "submitted" }}</span></p>
<h3>{{ item.get("title") or "Assignment Question" }}</h3>
<div style="white-space:pre-wrap;line-height:1.7">{{ item.get("description") or "No written question was provided." }}</div>
<div class="actions" style="margin-top:16px"><a class="btn" href="{{ url_for('assignment_question_download',assignment_id=item.get('id')) }}">⬇️ Download Question</a>{% if item.get("file_path") %}<a class="btn secondary" href="{{ url_for('assignment_file',assignment_id=item.get('id'),kind='original') }}">⬇️ Download Assignment File</a>{% endif %}</div>
</div>
{% if item.get("answer") %}<div class="card"><h3>Answer</h3><div style="white-space:pre-wrap;line-height:1.7">{{ item.get("answer") }}</div></div>{% endif %}
""", item=item)

@app.route("/assignments/<assignment_id>/question/download", methods=["GET"])
@login_required
def assignment_question_download(assignment_id):
    item = first_row("assignments", {"id": assignment_id})
    if not item:
        return "Assignment not found.", 404
    user = current_user()
    if not can_access_assignment(item, user):
        return "You are not authorized to download this assignment question.", 403
    title = item.get("title") or "Assignment"
    tracking = item.get("tracking_code") or "—"
    status = item.get("status") or "submitted"
    question = item.get("description") or "No written question was provided."
    text = f"KOJA AFRICA — ASSIGNMENT QUESTION\n\nTitle: {title}\nTracking Code: {tracking}\nStatus: {status}\n\nQUESTION / DESCRIPTION\n{question}\n"
    filename = re.sub(r"[^A-Za-z0-9._-]+", "-", str(title)).strip("-") or "assignment"
    filename = f"{filename}-question.txt"
    return send_file(io.BytesIO(text.encode("utf-8")), download_name=filename, mimetype="text/plain", as_attachment=True)

@app.route("/assignments/<assignment_id>/file/<kind>")
@login_required
def assignment_file(assignment_id, kind):
    item=first_row("assignments",{"id":assignment_id})
    if not item:
        return "Assignment not found.",404
    user=current_user()
    if not can_access_assignment(item,user):
        return "You are not authorized to access this assignment document.",403
    field_map={
        "original":("file_path","file_name","mime_type"),
        "answer":("answer_file_path","answer_file_name","mime_type"),
        "answered":("answered_file_path","answered_file_name","mime_type"),
    }
    if kind not in field_map:
        return "Invalid file type.",400
    path_field,name_field,mime_field=field_map[kind]
    path=item.get(path_field)
    if not path:
        return "File not found.",404
    try:
        r=requests.get(sb_storage_url(path),headers=sb_headers(),timeout=60)
        if not r.ok:
            return "File could not be retrieved.",404
        return send_file(io.BytesIO(r.content),download_name=item.get(name_field) or "assignment-file",
                         mimetype=item.get(mime_field) or "application/octet-stream",as_attachment=True)
    except Exception:
        logger.exception("Assignment file retrieval failed")
        return "File could not be retrieved.",503

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
        return render_page("CV Preview",r"""
<div class="card">
<h1>{{ data.full_name }}</h1><p>{{ data.phone }} | {{ data.email }} | {{ data.address }}</p>
{% if data.profile %}<h2>Professional Profile</h2><p>{{ data.profile }}</p>{% endif %}
{% if data.education %}<h2>Education</h2><p style="white-space:pre-wrap">{{ data.education }}</p>{% endif %}
{% if data.experience %}<h2>Work Experience</h2><p style="white-space:pre-wrap">{{ data.experience }}</p>{% endif %}
{% if data.skills %}<h2>Skills</h2><p style="white-space:pre-wrap">{{ data.skills }}</p>{% endif %}
{% if data.references %}<h2>References</h2><p style="white-space:pre-wrap">{{ data.references }}</p>{% endif %}
<hr><button onclick="window.print()">Print / Save as PDF</button>
</div>
""",data=data)

    return render_page("CV Builder",r"""
<div class="card"><h2>CV Builder</h2>
<form method="post">
<label>Full Name</label><input name="full_name" value="{{ user.name }}" required>
<label>Phone</label><input name="phone" value="{{ user.phone or '' }}">
<label>Email</label><input name="email" value="{{ user.email or '' }}" required>
<label>Address</label><input name="address">
<label>Professional Profile</label><textarea name="profile"></textarea>
<label>Education</label><textarea name="education"></textarea>
<label>Work Experience</label><textarea name="experience"></textarea>
<label>Skills</label><textarea name="skills"></textarea>
<label>References</label><textarea name="references"></textarea>
<button type="submit">Generate CV</button>
</form>
<p class="small">Use Print / Save as PDF in the Android browser. No ReportLab package is required.</p>
</div>
""")

# ============================================================
# DOCTORS / TEACHERS
# ============================================================

@app.route("/doctors")
@login_required
def doctors():
    doctors=db_select("doctor_profiles",order="created_at.desc",limit=100)
    return render_page("Doctors",r"""
<div class="hero"><h2>Find a Doctor</h2><p>Choose a specific doctor and request an appointment.</p></div>
<div class="grid">
{% for d in doctors %}
<div class="card">
<h3>{{ d.get("full_name") or d.get("doctor_name") or "Doctor" }}</h3>
<p><strong>Specialty:</strong> {{ d.get("specialty") or "General" }}</p>
<p><strong>Hospital/Clinic:</strong> {{ d.get("hospital_clinic") or "Not specified" }}</p>
{% if d.get("consultation_fee") %}<p><strong>Fee:</strong> {{ d.get("currency") or "ZMW" }} {{ d.get("consultation_fee") }}</p>{% endif %}
<div class="actions">
<a class="btn" href="{{ url_for('book_doctor',provider_id=(d.get('provider_id') or d.get('id'))) }}">Book This Doctor</a>
<a class="btn secondary" href="{{ url_for('provider_map',provider_id=(d.get('provider_id') or d.get('id')),provider_type='doctor') }}">View Location</a>
</div></div>
{% else %}<div class="card"><p>No doctor profiles have been registered yet.</p></div>{% endfor %}
</div>
""",doctors=doctors)

@app.route("/doctor/book/<provider_id>",methods=["GET","POST"])
@login_required
def book_doctor(provider_id):
    user=current_user()
    doctor=first_row("doctor_profiles",{"provider_id":provider_id}) or first_row("doctor_profiles",{"id":provider_id})
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
    return render_page("Book Doctor",r"""
<div class="card"><h2>Book {{ doctor.get("full_name") or doctor.get("doctor_name") or "Doctor" }}</h2>
<p><strong>Specialty:</strong> {{ doctor.get("specialty") or "General" }}</p>
<form method="post">
<label>Date</label><input type="date" name="appointment_date" required>
<label>Start Time</label><input type="time" name="start_time" required>
<label>End Time</label><input type="time" name="end_time">
<label>Location</label><input name="location" placeholder="Hospital, clinic or online">
<label>Notes</label><textarea name="notes"></textarea>
<button type="submit">Request Appointment</button>
</form></div>
""",doctor=doctor)

@app.route("/teachers")
@login_required
def teachers():
    teachers=db_select("teacher_profiles",order="created_at.desc",limit=100)
    return render_page("Teachers",r"""
<div class="hero"><h2>Find a Teacher / Tutor</h2><p>Choose a specific teacher for tutoring.</p></div>
<div class="grid">
{% for t in teachers %}
<div class="card">
<h3>{{ t.get("full_name") or t.get("teacher_name") or "Teacher" }}</h3>
<p><strong>Subjects:</strong> {{ t.get("subjects") or "Not specified" }}</p>
<p><strong>Grades:</strong> {{ t.get("grade_levels") or "Not specified" }}</p>
<p><strong>Qualification:</strong> {{ t.get("qualification") or "Not specified" }}</p>
{% if t.get("hourly_rate") %}<p><strong>Rate:</strong> {{ t.get("currency") or "ZMW" }} {{ t.get("hourly_rate") }}/hour</p>{% endif %}
<a class="btn" href="{{ url_for('book_teacher',provider_id=(t.get('provider_id') or t.get('id'))) }}">Book Teacher</a>
<a class="btn secondary" href="{{ url_for('provider_map',provider_id=(t.get('provider_id') or t.get('id')),provider_type='teacher') }}">View Location</a>
</div>
{% else %}<div class="card"><p>No teacher profiles have been registered yet.</p></div>{% endfor %}
</div>
""",teachers=teachers)

@app.route("/teacher/book/<provider_id>",methods=["GET","POST"])
@login_required
def book_teacher(provider_id):
    user=current_user()
    teacher=first_row("teacher_profiles",{"provider_id":provider_id}) or first_row("teacher_profiles",{"id":provider_id})
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
    return render_page("Book Teacher",r"""
<div class="card"><h2>Book {{ teacher.get("full_name") or teacher.get("teacher_name") or "Teacher" }}</h2>
<p>{{ teacher.get("subjects") or "" }}</p>
<form method="post">
<label>Date</label><input type="date" name="appointment_date" required>
<label>Start Time</label><input type="time" name="start_time" required>
<label>End Time</label><input type="time" name="end_time">
<label>Location / Online</label><input name="location">
<label>Notes</label><textarea name="notes"></textarea>
<button type="submit">Book Teacher</button>
</form></div>
""",teacher=teacher)

# ============================================================
# ALL PROFESSIONAL SERVICES
# ============================================================

PROFESSIONAL_CATEGORIES = [
    "Lawyer / Legal Services", "Accountant / Auditor", "Engineer", "Architect",
    "IT / Software / Web Developer", "Graphic Designer", "Consultant",
    "Counsellor / Psychologist", "Social Worker", "Nurse / Midwife",
    "Pharmacist", "Dentist", "Nutritionist / Dietitian", "Physiotherapist",
    "Real Estate Agent", "Insurance Agent", "Financial Adviser", "Teacher / Tutor",
    "Doctor / Medical Practitioner", "Electrician", "Plumber", "Mechanic",
    "Builder / Contractor", "Carpenter", "Welder", "Tailor / Fashion Designer",
    "Hairdresser / Barber / Beauty Professional", "Photographer / Videographer",
    "Writer / Editor / Translator", "Marketing / Advertising", "Business Consultant",
    "Other Professional Service"
]

# ============================================================
# PUBLIC KOJA FEED — Facebook-style public wall
# Everyone can VIEW. Logged-in users can POST, LIKE and COMMENT.
# Supports text, news/updates and public images.
# ============================================================
PUBLIC_FEED_SQL = """
create extension if not exists pgcrypto;
create table if not exists public.koja_public_posts (
 id uuid primary key default gen_random_uuid(), author_id uuid not null,
 post_type text not null default 'update', title text, body text not null,
 media_url text, media_type text, created_at timestamptz default now(),
 updated_at timestamptz default now(), is_published boolean default true
);
create index if not exists koja_public_posts_feed_idx on public.koja_public_posts(is_published, created_at desc);
create index if not exists koja_public_posts_author_idx on public.koja_public_posts(author_id, created_at desc);
create table if not exists public.koja_public_likes (
 post_id uuid not null references public.koja_public_posts(id) on delete cascade,
 user_id uuid not null, created_at timestamptz default now(), primary key(post_id,user_id)
);
create index if not exists koja_public_likes_post_idx on public.koja_public_likes(post_id);
create table if not exists public.koja_public_comments (
 id uuid primary key default gen_random_uuid(),
 post_id uuid not null references public.koja_public_posts(id) on delete cascade,
 author_id uuid not null, body text not null, created_at timestamptz default now()
);
create index if not exists koja_public_comments_post_idx on public.koja_public_comments(post_id,created_at);
"""

@app.route('/public')
def public_feed():
    # db_select returns a list (not a (rows, error) tuple).
    # Keep the public page resilient: an unavailable/missing table simply shows an empty feed.
    rows = db_select('koja_public_posts', {'is_published':'eq.true'}, order='created_at.desc', limit=50) or []
    enriched=[]
    for post in rows or []:
        author=first_row('profiles', {'id':post.get('author_id')}) or {}
        likes = db_select('koja_public_likes', {'post_id':post.get('id')}, select='user_id', limit=500) or []
        comments = db_select('koja_public_comments', {'post_id':post.get('id')}, order='created_at.asc', limit=100) or []
        comment_rows=[]
        for c in comments or []:
            ca=first_row('profiles', {'id':c.get('author_id')}) or {}
            comment_rows.append({**c,'author_name':ca.get('full_name') or ca.get('name') or ca.get('email') or 'KOJA User'})
        uid=(current_user() or {}).get('id')
        enriched.append({**post,'author_name':author.get('full_name') or author.get('name') or author.get('email') or 'KOJA User',
            'like_count':len(likes or []),'liked':bool(uid and any(str(x.get('user_id'))==str(uid) for x in (likes or []))), 'comments':comment_rows})
    return render_page('KOJA Public — News, Updates & Media', r'''
<div class="hero"><h1>🌍 KOJA Public</h1><p>News, updates, public messages and images from the KOJA community. Everyone can view this page.</p></div>
{% if user %}<div class="card"><h3>📝 Share with everyone</h3>
<form method="post" action="{{ url_for('public_feed_create') }}" enctype="multipart/form-data">
<div class="grid"><div><label>Type</label><select name="post_type"><option value="update">Community Update</option><option value="news">News</option><option value="announcement">Announcement</option><option value="event">Event</option></select></div><div><label>Title (optional)</label><input name="title" maxlength="180" placeholder="What is this about?"></div></div>
<label>Message</label><textarea name="body" maxlength="5000" placeholder="Write a public message, update or news..." required></textarea>
<label>Image / media (optional)</label><input type="file" name="media" accept="image/jpeg,image/png,image/webp">
<button class="btn" type="submit">🌐 Publish Publicly</button></form>
<p class="small">Your post is public and may be visible to people who are not logged in.</p></div>
{% else %}<div class="card"><strong>Want to publish?</strong> <a class="btn" href="{{ url_for('login', next='/public') }}">Login</a> <a class="btn secondary" href="{{ url_for('register', next='/public') }}">Create account</a></div>{% endif %}
<div class="card"><h2>📰 News & Updates</h2><p class="small">Public feed · newest first</p></div>
{% for p in posts %}<article class="card" id="post-{{ p.id }}"><strong>👤 {{ p.author_name }}</strong><div class="small">{{ p.post_type|title }} · {{ p.created_at }}</div>
{% if p.title %}<h2 style="margin-top:10px">{{ p.title }}</h2>{% endif %}<p style="white-space:pre-wrap;line-height:1.7">{{ p.body }}</p>
{% if p.media_url %}<img src="{{ p.media_url }}" alt="Public KOJA post image" loading="lazy" style="width:100%;max-height:620px;object-fit:cover;border-radius:12px;margin-top:8px">{% endif %}
<div class="actions" style="margin-top:12px">{% if user %}<form method="post" action="{{ url_for('public_toggle_like', post_id=p.id) }}" style="display:inline"><button class="btn secondary" type="submit">{{ '❤️ Liked' if p.liked else '🤍 Like' }} · {{ p.like_count }}</button></form>{% else %}<a class="btn secondary" href="{{ url_for('login', next='/public') }}">🤍 Like · {{ p.like_count }}</a>{% endif %}<span class="btn secondary" style="cursor:default">💬 {{ p.comments|length }} Comments</span></div>
{% for c in p.comments %}<div style="padding:9px 0;border-top:1px solid var(--border);margin-top:9px"><strong>{{ c.author_name }}</strong><div>{{ c.body }}</div><div class="small">{{ c.created_at }}</div></div>{% endfor %}
{% if user %}<form method="post" action="{{ url_for('public_comment', post_id=p.id) }}"><input name="body" maxlength="1000" placeholder="Write a comment..." required><button class="btn" type="submit">Comment</button></form>{% else %}<p class="small"><a href="{{ url_for('login', next='/public') }}">Login</a> to comment.</p>{% endif %}
</article>{% else %}<div class="card"><h3>No public updates yet.</h3><p>Be the first KOJA user to share a public update or news.</p></div>{% endfor %}
''', posts=enriched)

@app.route('/public/create', methods=['POST'])
@login_required
def public_feed_create():
    body=clean(request.form.get('body')); title=clean(request.form.get('title'))
    post_type=clean(request.form.get('post_type')).lower() or 'update'
    if post_type not in {'update','news','announcement','event'}: post_type='update'
    if not body: flash('Write a message before publishing.','danger'); return redirect(url_for('public_feed'))
    media=request.files.get('media'); uploaded=None
    if media and media.filename:
        ext=media.filename.lower().rsplit('.',1)[-1] if '.' in media.filename else ''
        if ext not in {'jpg','jpeg','png','webp'}: flash('Public feed images must be JPG, PNG or WebP.','danger'); return redirect(url_for('public_feed'))
        uploaded,err=upload_storage(media,'public-feed')
        if err: flash(f'Image upload failed: {err}','danger'); return redirect(url_for('public_feed'))
    payload={'author_id':current_user().get('id'),'post_type':post_type,'title':title or None,'body':body,
             'media_url':(uploaded or {}).get('url'),'media_type':('image' if uploaded else None),'is_published':True}
    _,err=db_insert('koja_public_posts',payload)
    flash('Published to KOJA Public.' if not err else 'Public post could not be published. Run the updated KOJA_CONNECT.sql first.','success' if not err else 'danger')
    return redirect(url_for('public_feed'))

@app.route('/public/like/<post_id>', methods=['POST'])
@login_required
def public_toggle_like(post_id):
    uid=current_user().get('id'); existing=first_row('koja_public_likes', {'post_id':post_id,'user_id':uid})
    if existing: db_delete('koja_public_likes', {'post_id':post_id,'user_id':uid})
    else: db_insert('koja_public_likes', {'post_id':post_id,'user_id':uid})
    return redirect(url_for('public_feed')+'#post-'+post_id)

@app.route('/public/comment/<post_id>', methods=['POST'])
@login_required
def public_comment(post_id):
    body=clean(request.form.get('body'))
    if body: db_insert('koja_public_comments', {'post_id':post_id,'author_id':current_user().get('id'),'body':body})
    return redirect(url_for('public_feed')+'#post-'+post_id)


# ============================================================
# KOJA DIGITAL MARKETPLACE
# ============================================================

MARKETPLACE_SQL = r'''
create table if not exists public.koja_marketplace_products (
 id uuid primary key default gen_random_uuid(),
 seller_id uuid not null,
 title text not null,
 description text not null,
 category text not null default 'Other',
 price numeric(12,2) not null default 0 check (price >= 0),
 currency text not null default 'ZMW',
 cover_url text,
 contact_phone text,
 contact_email text,
 whatsapp_number text,
 preferred_contact text,
 contact_phone_public boolean default false,
 contact_email_public boolean default false,
 whatsapp_public boolean default false,
 location text,
 town text,
 country text,
 continent text,
 file_url text,
 file_name text,
 file_size bigint,
 is_published boolean not null default false,
 created_at timestamptz not null default now(),
 updated_at timestamptz not null default now()
);
create index if not exists koja_marketplace_products_feed_idx on public.koja_marketplace_products(is_published, created_at desc);
create index if not exists koja_marketplace_products_seller_idx on public.koja_marketplace_products(seller_id, created_at desc);

create table if not exists public.koja_marketplace_orders (
 id uuid primary key default gen_random_uuid(),
 product_id uuid not null references public.koja_marketplace_products(id) on delete cascade,
 buyer_id uuid not null,
 seller_id uuid not null,
 amount numeric(12,2) not null default 0,
 currency text not null default 'ZMW',
 status text not null default 'pending',
 payment_method text,
 payment_reference text,
 payment_transaction_id text,
 created_at timestamptz not null default now(),
 updated_at timestamptz not null default now()
);
create index if not exists koja_marketplace_orders_buyer_idx on public.koja_marketplace_orders(buyer_id, created_at desc);
create index if not exists koja_marketplace_orders_seller_idx on public.koja_marketplace_orders(seller_id, created_at desc);
create unique index if not exists koja_marketplace_free_order_unique on public.koja_marketplace_orders(product_id, buyer_id) where amount = 0;

create table if not exists public.koja_marketplace_posts (
 id uuid primary key default gen_random_uuid(),
 author_id uuid not null,
 product_id uuid references public.koja_marketplace_products(id) on delete set null,
 title text,
 body text not null,
 media_url text,
 media_type text,
 created_at timestamptz not null default now(),
 updated_at timestamptz not null default now(),
 is_published boolean not null default true
);
create index if not exists koja_marketplace_posts_feed_idx on public.koja_marketplace_posts(is_published, created_at desc);
create index if not exists koja_marketplace_posts_author_idx on public.koja_marketplace_posts(author_id, created_at desc);
create index if not exists koja_marketplace_posts_product_idx on public.koja_marketplace_posts(product_id, created_at desc);
'''

MARKETPLACE_CATEGORIES = [
    'Ebooks & Books','Courses & Learning','Research & Academic','Templates & Documents',
    'Software & Code','Graphics & Design','Music & Audio','Video & Media',
    'Business Resources','Other'
]
MARKETPLACE_FILE_EXTENSIONS = {
    'pdf','doc','docx','txt','zip','csv','xlsx','xls','ppt','pptx',
    'jpg','jpeg','png','webp','mp3','wav','m4a','mp4','webm','py','html','css','js','json'
}

def marketplace_product(product_id):
    return first_row('koja_marketplace_products', {'id': product_id})

def marketplace_seller_name(user_id):
    u=find_user_by_id(user_id) or {}
    return first_nonempty(u.get('full_name'),u.get('name'),u.get('email'),'KOJA Seller')

def marketplace_money(value,currency='ZMW'):
    try: return f"{currency} {float(value or 0):,.2f}"
    except Exception: return f"{currency} 0.00"

def marketplace_has_access(product,user_id):
    if not product or not user_id: return False
    if str(product.get('seller_id'))==str(user_id): return True
    try:
        if float(product.get('price') or 0)<=0: return True
    except Exception: pass
    return bool(first_row('koja_marketplace_orders',{'product_id':product.get('id'),'buyer_id':user_id,'status':'eq.paid'}))

def marketplace_post_author_name(user_id):
    return marketplace_seller_name(user_id)

def marketplace_post_storage_path(media_url):
    media_url=clean(media_url); storage_path=''
    public_prefix=f"{SUPABASE_URL.rstrip('/')}/storage/v1/object/public/" if SUPABASE_URL else ''
    if public_prefix and media_url.startswith(public_prefix):
        rem=media_url[len(public_prefix):]
        bp=f"{STORAGE_BUCKET}/"
        if rem.startswith(bp): storage_path=unquote(rem[len(bp):])
    if not storage_path:
        storage_path=media_url.lstrip('/')
        if storage_path.startswith(f"{STORAGE_BUCKET}/"):
            storage_path=storage_path[len(STORAGE_BUCKET)+1:]
    return storage_path

@app.route('/marketplace/post-media/<post_id>')
def marketplace_post_media(post_id):
    post=first_row('koja_marketplace_posts', {'id':post_id})
    if not post or not post.get('is_published') or not post.get('media_url'): abort(404)
    storage_path=marketplace_post_storage_path(post.get('media_url'))
    if not storage_path or not supabase_configured(): abort(404)
    try:
        r=requests.get(sb_storage_url(storage_path),headers=sb_headers(),timeout=30)
        if not r.ok: abort(404)
        response=send_file(io.BytesIO(r.content),mimetype=r.headers.get('Content-Type') or post.get('media_type') or 'application/octet-stream',max_age=3600)
        response.headers['Cache-Control']='public, max-age=3600'
        return response
    except Exception:
        abort(404)

@app.route('/marketplace/post',methods=['GET','POST'])
@login_required
def marketplace_post_create():
    if request.method=='POST':
        title=clean(request.form.get('title'))
        body=clean(request.form.get('body'))
        product_id=clean(request.form.get('product_id')) or None
        if not body:
            flash('Write something for your marketplace post.','danger')
            return redirect(url_for('marketplace_post_create'))
        if product_id:
            product=marketplace_product(product_id)
            if not product or (not product.get('is_published') and str(product.get('seller_id'))!=str((current_user() or {}).get('id'))):
                product_id=None
        image=request.files.get('image')
        video=request.files.get('video')
        if image and image.filename and video and video.filename:
            flash('Choose an image OR a video for one post, not both.','danger')
            return redirect(url_for('marketplace_post_create'))
        media_url=None; media_type=None
        media=image if image and image.filename else video if video and video.filename else None
        if media:
            ext=media.filename.lower().rsplit('.',1)[-1] if '.' in media.filename else ''
            if image and image.filename:
                if ext not in {'jpg','jpeg','png','webp'}:
                    flash('Marketplace images must be JPG, JPEG, PNG or WEBP.','danger')
                    return redirect(url_for('marketplace_post_create'))
                folder='marketplace/posts/images'; media_type='image'
            else:
                if ext not in {'mp4','webm','mov'}:
                    flash('Marketplace videos must be MP4, WEBM or MOV.','danger')
                    return redirect(url_for('marketplace_post_create'))
                folder='marketplace/posts/videos'; media_type='video'
            uploaded,err=upload_storage(media,folder)
            if err:
                flash(f'Media upload failed: {err}','danger')
                return redirect(url_for('marketplace_post_create'))
            media_url=(uploaded or {}).get('url')
        _,err=db_insert('koja_marketplace_posts',{
            'author_id':(current_user() or {}).get('id'),
            'product_id':product_id,
            'title':title or None,
            'body':body,
            'media_url':media_url,
            'media_type':media_type,
            'is_published':True,
            'updated_at':utc_now()
        })
        flash('Marketplace post published.' if not err else 'Post could not be saved. Run the updated MARKETPLACE.sql in Supabase.','success' if not err else 'danger')
        return redirect(url_for('marketplace'))
    uid=(current_user() or {}).get('id')
    products=db_select('koja_marketplace_products',{'seller_id':uid},order='created_at.desc',limit=100) or []
    return render_page('Create Marketplace Post',r'''<div class="hero"><h1>📣 Create Marketplace Post</h1><p>Promote a product, announce an offer, share an image, or publish a marketplace video.</p></div><div class="card"><form method="post" enctype="multipart/form-data"><label>Post title (optional)</label><input name="title" maxlength="180" placeholder="e.g. New Grade 12 Revision Guide available"><label>Post</label><textarea name="body" maxlength="10000" required placeholder="Tell buyers what you are offering..."></textarea><label>Link to your product (optional)</label><select name="product_id"><option value="">No product link</option>{% for p in products %}<option value="{{ p.id }}">{{ p.title }}</option>{% endfor %}</select><div class="grid"><div><label>Image (optional)</label><input type="file" name="image" accept="image/jpeg,image/png,image/webp"></div><div><label>Video (optional)</label><input type="file" name="video" accept="video/mp4,video/webm,video/quicktime"></div></div><button class="btn" type="submit">🚀 Publish Post</button></form><p class="small">Maximum media upload: {{ max_mb }} MB. Use either an image or a video per post.</p></div>''',products=products,max_mb=MAX_UPLOAD_MB)

@app.route('/marketplace')
def marketplace():
    q=clean(request.args.get('q')); category=clean(request.args.get('category'))
    rows=db_select('koja_marketplace_products',{'is_published':'eq.true'},order='created_at.desc',limit=100) or []
    if q:
        n=q.lower(); rows=[r for r in rows if n in str(r.get('title') or '').lower() or n in str(r.get('description') or '').lower() or n in str(r.get('category') or '').lower()]
    if category: rows=[r for r in rows if str(r.get('category') or '')==category]
    products=[{**r,'seller_name':marketplace_seller_name(r.get('seller_id')),'price_display':marketplace_money(r.get('price'),r.get('currency') or 'ZMW')} for r in rows]
    post_rows=db_select('koja_marketplace_posts',{'is_published':'eq.true'},order='created_at.desc',limit=50) or []
    pids=[str(x.get('product_id')) for x in post_rows if x.get('product_id')]
    post_products={str(p.get('id')):p for p in (db_select('koja_marketplace_products',{'id':'in.('+','.join(pids)+')'},limit=100) if pids else [])}
    posts=[{**r,'author_name':marketplace_post_author_name(r.get('author_id')),'product':post_products.get(str(r.get('product_id')))} for r in post_rows]
    return render_page('Marketplace',r'''
<div class="hero"><h1>🛒 KOJA Digital Marketplace</h1><p>Discover, buy and sell digital products across Africa — ebooks, courses, research resources, templates, software, graphics, audio and more.</p><div class="actions"><a class="btn" href="{{ url_for('marketplace_sell') if user else url_for('login', next='/marketplace/sell') }}">💼 Sell a Digital Product</a>{% if user %}<a class="btn secondary" href="{{ url_for('marketplace_my') }}">📦 My Marketplace</a>{% endif %}</div></div>
<div class="card"><form method="get"><div class="grid"><div><label>Search</label><input name="q" value="{{ q }}" placeholder="Search digital products..."></div><div><label>Category</label><select name="category"><option value="">All categories</option>{% for c in categories %}<option value="{{ c }}" {% if category==c %}selected{% endif %}>{{ c }}</option>{% endfor %}</select></div></div><button class="btn" type="submit">🔎 Search Marketplace</button></form></div>
<div class="card"><div class="actions" style="justify-content:space-between"><h2 style="margin:0">📣 Marketplace Posts</h2>{% if user %}<a class="btn" href="{{ url_for('marketplace_post_create') }}">+ Post</a>{% endif %}</div>{% for p in posts %}<article class="card" style="margin-top:14px"><div class="small">👤 {{ p.author_name }} · {{ p.created_at }}</div>{% if p.title %}<h3 style="margin:8px 0">{{ p.title }}</h3>{% endif %}<p style="white-space:pre-wrap;line-height:1.6">{{ p.body }}</p>{% if p.media_url and p.media_type=='image' %}<img src="{{ url_for('marketplace_post_media', post_id=p.id) }}" alt="Marketplace post image" loading="lazy" style="display:block;width:100%;max-height:620px;object-fit:contain;border-radius:12px;background:var(--bg)">{% elif p.media_url and p.media_type=='video' %}<video controls preload="metadata" playsinline style="display:block;width:100%;max-height:620px;border-radius:12px;background:#000"><source src="{{ url_for('marketplace_post_media', post_id=p.id) }}"></video>{% endif %}{% if p.product and p.product.is_published %}<div class="actions" style="margin-top:12px"><a class="btn" href="{{ url_for('marketplace_product_view', product_id=p.product.id) }}">🛒 View {{ p.product.title }}</a></div>{% endif %}</article>{% else %}<p class="small">No marketplace posts yet. Publish the first one.</p>{% endfor %}</div>
<div class="grid">{% for p in products %}<article class="card"><div style="aspect-ratio:16/9;background:var(--bg);border-radius:10px;overflow:hidden;display:grid;place-items:center">{% if p.cover_url %}<img src="{{ url_for('marketplace_cover', product_id=p.id) }}" alt="{{ p.title }}" loading="lazy" style="width:100%;height:100%;object-fit:cover">{% else %}<div style="font-size:52px">📄</div>{% endif %}</div><div class="small" style="margin-top:10px">{{ p.category }} · by {{ p.seller_name }}</div><h2 style="margin:6px 0">{{ p.title }}</h2><p style="min-height:48px">{{ p.description[:180] }}{% if p.description|length>180 %}…{% endif %}</p><strong style="font-size:20px">{{ p.price_display if p.price|float > 0 else 'FREE' }}</strong><div class="actions" style="margin-top:12px"><a class="btn" href="{{ url_for('marketplace_product_view', product_id=p.id) }}">View Product</a></div></article>{% else %}<div class="card"><h3>No products found yet.</h3><p>Be the first seller to publish a digital product.</p></div>{% endfor %}</div>
''',products=products,posts=posts,q=q,category=category,categories=MARKETPLACE_CATEGORIES)

@app.route('/marketplace/product/<product_id>')
def marketplace_product_view(product_id):
    product=marketplace_product(product_id)
    if not product or not product.get('is_published'): abort(404)
    seller=marketplace_seller_name(product.get('seller_id')); uid=(current_user() or {}).get('id') if current_user() else None
    return render_page(product.get('title') or 'Digital Product',r'''
<div class="card"><div class="small">{{ product.category }} · Seller: {{ seller }}</div><h1>{{ product.title }}</h1>{% if product.cover_url %}<img src="{{ url_for('marketplace_cover', product_id=product.id) }}" alt="{{ product.title }}" style="display:block;width:100%;max-height:520px;object-fit:contain;border-radius:12px;background:var(--bg)">{% endif %}<p style="white-space:pre-wrap;line-height:1.75">{{ product.description }}</p><div class="card"><h3>👤 Seller Information</h3><p><strong>Seller:</strong> {{ seller }}</p>{% if product.location or product.town or product.country or product.continent %}<p>📍 {{ product.location or '' }}{% if product.town %}, {{ product.town }}{% endif %}{% if product.country %}, {{ product.country }}{% endif %}{% if product.continent %} · {{ product.continent }}{% endif %}</p>{% endif %}{% if product.contact_phone and product.contact_phone_public %}<p>📞 {{ product.contact_phone }}</p>{% endif %}{% if product.contact_email and product.contact_email_public %}<p>✉️ {{ product.contact_email }}</p>{% endif %}{% if product.whatsapp_number and product.whatsapp_public %}<p>💬 WhatsApp: {{ product.whatsapp_number }}</p>{% endif %}<div class="actions"><a class="btn" href="{{ url_for('marketplace_chat', seller_id=product.seller_id, product_id=product.id) }}">💬 Contact Seller</a>{% if product.contact_phone and product.contact_phone_public %}<a class="btn secondary" href="tel:{{ product.contact_phone }}">📞 Call</a>{% endif %}{% if product.whatsapp_number and product.whatsapp_public %}<a class="btn secondary" target="_blank" rel="noopener" href="https://wa.me/{{ product.whatsapp_number|replace('+','')|replace(' ','') }}">WhatsApp</a>{% endif %}</div></div><h2>{{ 'FREE' if product.price|float<=0 else money(product.price, product.currency) }}</h2>{% if user %}{% if access %}<a class="btn success" href="{{ url_for('marketplace_download', product_id=product.id) }}">⬇️ Download / Access</a>{% elif product.price|float<=0 %}<form method="post" action="{{ url_for('marketplace_buy', product_id=product.id) }}"><button class="btn success" type="submit">🎁 Get Free Product</button></form>{% else %}<form method="post" action="{{ url_for('marketplace_buy', product_id=product.id) }}"><button class="btn" type="submit">🛒 Request Purchase · {{ money(product.price, product.currency) }}</button></form><p class="small">Secure checkout is handled by Flutterwave when FLW_SECRET_KEY is configured. KOJA verifies the transaction on the server before releasing the digital file.</p>{% endif %}{% else %}<a class="btn" href="{{ url_for('login', next=request.path) }}">Login to Purchase / Download</a>{% endif %}</div>
''',product=product,seller=seller,access=marketplace_has_access(product,uid),money=marketplace_money)

@app.route('/marketplace/buy/<product_id>',methods=['POST'])
@login_required
def marketplace_buy(product_id):
    product=marketplace_product(product_id); user=current_user() or {}; uid=user.get('id')
    if not product or not product.get('is_published'): abort(404)
    try: amount=float(product.get('price') or 0)
    except Exception: amount=0
    if amount<=0:
        existing=first_row('koja_marketplace_orders',{'product_id':product_id,'buyer_id':uid,'status':'eq.paid'})
        if not existing:
            _,err=db_insert('koja_marketplace_orders',{'product_id':product_id,'buyer_id':uid,'seller_id':product.get('seller_id'),'amount':0,'currency':product.get('currency') or 'ZMW','status':'paid','payment_method':'free','payment_reference':'FREE-'+secrets.token_hex(8),'updated_at':utc_now()})
            if err: flash('Could not create the free-product order. Run MARKETPLACE.sql in Supabase first.','danger'); return redirect(url_for('marketplace_product_view',product_id=product_id))
        flash('Free product added to your purchases.','success')
        return redirect(url_for('marketplace_download',product_id=product_id))

    if not FLW_SECRET_KEY:
        flash('Online payment is not configured yet. Add FLW_SECRET_KEY to Render Environment Variables.','warning')
        return redirect(url_for('marketplace_product_view',product_id=product_id))
    email=clean(user.get('email')).lower()
    if not email:
        flash('Your account needs an email address before payment can start.','warning')
        return redirect(url_for('marketplace_product_view',product_id=product_id))
    tx_ref='KOJA-MKT-'+uuid.uuid4().hex[:24]
    order,err=db_insert('koja_marketplace_orders',{'product_id':product_id,'buyer_id':uid,'seller_id':product.get('seller_id'),'amount':amount,'currency':product.get('currency') or 'ZMW','status':'pending','payment_method':'flutterwave','payment_reference':tx_ref,'updated_at':utc_now()})
    if err or not order:
        flash('Marketplace order could not be created. Run MARKETPLACE.sql in Supabase first.','danger')
        return redirect(url_for('marketplace_product_view',product_id=product_id))
    payload={'tx_ref':tx_ref,'amount':amount,'currency':product.get('currency') or 'ZMW','redirect_url':url_for('marketplace_payment_callback',_external=True),'customer':{'email':email,'name':first_nonempty(user.get('name'),email),'phonenumber':user.get('phone') or ''},'customizations':{'title':'KOJA AFRICA Marketplace','description':product.get('title') or 'Digital product'}}
    try:
        r=requests.post(FLW_BASE_URL+'/payments',headers={'Authorization':'Bearer '+FLW_SECRET_KEY,'Content-Type':'application/json'},json=payload,timeout=30)
        data=json_or_empty(r)
        link=((data.get('data') or {}).get('link')) if isinstance(data,dict) else None
        if r.ok and link:
            return redirect(link)
        logger.error('Flutterwave checkout creation failed: %s %s',r.status_code,str(data)[:1500])
    except Exception as exc:
        logger.exception('Flutterwave checkout error: %s',exc)
    flash('Payment checkout could not be started. Please try again.','danger')
    return redirect(url_for('marketplace_product_view',product_id=product_id))

@app.route('/marketplace/payment/callback')
@login_required
def marketplace_payment_callback():
    tx_ref=clean(request.args.get('tx_ref')); transaction_id=clean(request.args.get('transaction_id')); status=clean(request.args.get('status')).lower(); uid=(current_user() or {}).get('id')
    if not tx_ref or not transaction_id:
        flash('Payment response was incomplete.','danger'); return redirect(url_for('marketplace_my'))
    order=first_row('koja_marketplace_orders',{'payment_reference':tx_ref,'buyer_id':uid})
    if not order:
        flash('Marketplace payment order could not be found.','danger'); return redirect(url_for('marketplace_my'))
    if not FLW_SECRET_KEY:
        flash('Payment verification is not configured.','danger'); return redirect(url_for('marketplace_my'))
    try:
        r=requests.get(FLW_BASE_URL+'/transactions/'+transaction_id+'/verify',headers={'Authorization':'Bearer '+FLW_SECRET_KEY,'Content-Type':'application/json'},timeout=30)
        body=json_or_empty(r); tx=(body.get('data') or {}) if isinstance(body,dict) else {}
        expected_amount=float(order.get('amount') or 0); paid_amount=float(tx.get('amount') or 0); expected_currency=str(order.get('currency') or 'ZMW').upper(); paid_currency=str(tx.get('currency') or '').upper()
        valid=(r.ok and tx.get('status')=='successful' and str(tx.get('tx_ref'))==tx_ref and paid_currency==expected_currency and paid_amount>=expected_amount)
        if valid:
            db_update('koja_marketplace_orders',{'id':order.get('id')},{'status':'paid','payment_method':'flutterwave','payment_reference':tx_ref,'payment_transaction_id':str(tx.get('id') or transaction_id),'updated_at':utc_now()})
            flash('Payment verified successfully. Your digital product is now available.','success')
            return redirect(url_for('marketplace_download',product_id=order.get('product_id')))
        db_update('koja_marketplace_orders',{'id':order.get('id')},{'status':'failed' if status in ('failed','cancelled') else 'pending','updated_at':utc_now()})
    except Exception as exc:
        logger.exception('Flutterwave verification error: %s',exc)
    flash('Payment was not verified, so the digital product has not been released.','warning')
    return redirect(url_for('marketplace_my'))

@app.route('/marketplace/cover/<product_id>')
def marketplace_cover(product_id):
    product=marketplace_product(product_id)
    if not product or not product.get('cover_url'): abort(404)
    media_url=clean(product.get('cover_url')); storage_path=''
    public_prefix=f"{SUPABASE_URL.rstrip('/')}/storage/v1/object/public/" if SUPABASE_URL else ''
    if public_prefix and media_url.startswith(public_prefix):
        rem=media_url[len(public_prefix):]; bp=f"{STORAGE_BUCKET}/"
        if rem.startswith(bp): storage_path=unquote(rem[len(bp):])
    if not storage_path:
        storage_path=media_url.lstrip('/')
        if storage_path.startswith(f"{STORAGE_BUCKET}/"): storage_path=storage_path[len(STORAGE_BUCKET)+1:]
    if not storage_path or not supabase_configured(): abort(404)
    try:
        r=requests.get(sb_storage_url(storage_path),headers=sb_headers(),timeout=20)
        if not r.ok: abort(404)
        response=send_file(io.BytesIO(r.content),mimetype=r.headers.get('Content-Type') or 'image/jpeg',max_age=3600)
        response.headers['Cache-Control']='public, max-age=3600'
        return response
    except Exception:
        abort(404)

@app.route('/marketplace/download/<product_id>')
@login_required
def marketplace_download(product_id):
    product=marketplace_product(product_id); uid=(current_user() or {}).get('id')
    if not product or not product.get('is_published') or not marketplace_has_access(product,uid): abort(404)
    media_url=clean(product.get('file_url')); storage_path=''
    public_prefix=f"{SUPABASE_URL.rstrip('/')}/storage/v1/object/public/" if SUPABASE_URL else ''
    if public_prefix and media_url.startswith(public_prefix):
        rem=media_url[len(public_prefix):]; bp=f"{STORAGE_BUCKET}/"
        if rem.startswith(bp): storage_path=unquote(rem[len(bp):])
    if not storage_path:
        storage_path=media_url.lstrip('/')
        if storage_path.startswith(f"{STORAGE_BUCKET}/"): storage_path=storage_path[len(STORAGE_BUCKET)+1:]
    if not storage_path or not supabase_configured(): abort(404)
    try:
        r=requests.get(sb_storage_url(storage_path),headers=sb_headers(),timeout=30)
        if not r.ok: abort(404)
        filename=secure_filename(product.get('file_name') or 'koja-digital-product') or 'koja-digital-product'
        return send_file(io.BytesIO(r.content),download_name=filename,mimetype=r.headers.get('Content-Type') or 'application/octet-stream',max_age=0)
    except Exception as exc:
        logger.exception('Marketplace download failed: %s',exc); abort(404)

@app.route('/marketplace/sell',methods=['GET','POST'])
@login_required
def marketplace_sell():
    if request.method=='POST':
        title=clean(request.form.get('title')); description=clean(request.form.get('description')); category=clean(request.form.get('category')) or 'Other'
        try: price=float(request.form.get('price') or 0)
        except Exception: price=-1
        if not title or not description or price<0: flash('Title, description and a valid price are required.','danger'); return redirect(url_for('marketplace_sell'))
        if category not in MARKETPLACE_CATEGORIES: category='Other'
        digital=request.files.get('digital_file'); cover=request.files.get('cover')
        if not digital or not digital.filename: flash('Choose the digital product file to sell.','danger'); return redirect(url_for('marketplace_sell'))
        ext=digital.filename.lower().rsplit('.',1)[-1] if '.' in digital.filename else ''
        if ext not in MARKETPLACE_FILE_EXTENSIONS: flash('Unsupported digital file type.','danger'); return redirect(url_for('marketplace_sell'))
        uploaded,err=upload_storage(digital,'marketplace/products')
        if err: flash(f'Digital file upload failed: {err}','danger'); return redirect(url_for('marketplace_sell'))
        cover_url=None
        if cover and cover.filename:
            cext=cover.filename.lower().rsplit('.',1)[-1] if '.' in cover.filename else ''
            if cext in {'jpg','jpeg','png','webp'}:
                cu,cerr=upload_storage(cover,'marketplace/covers')
                if not cerr: cover_url=(cu or {}).get('url')
        payload={'seller_id':(current_user() or {}).get('id'),'title':title,'description':description,'category':category,'price':price,'currency':'ZMW','cover_url':cover_url,'contact_phone':clean(request.form.get('contact_phone')),'contact_email':clean(request.form.get('contact_email')).lower(),'whatsapp_number':clean(request.form.get('whatsapp_number')),'preferred_contact':clean(request.form.get('preferred_contact')) or 'KOJA Chat','contact_phone_public':bool(request.form.get('contact_phone_public')),'contact_email_public':bool(request.form.get('contact_email_public')),'whatsapp_public':bool(request.form.get('whatsapp_public')),'location':clean(request.form.get('location')),'town':clean(request.form.get('town')),'country':clean(request.form.get('country')),'continent':clean(request.form.get('continent')),'file_url':(uploaded or {}).get('url'),'file_name':digital.filename,'file_size':getattr(digital,'content_length',None),'is_published':False}
        _,err=db_insert('koja_marketplace_products',payload)
        flash('Product submitted. It is hidden until published/approved.' if not err else 'Product could not be saved. Run MARKETPLACE.sql in Supabase first.','success' if not err else 'danger')
        return redirect(url_for('marketplace_my'))
    return render_page('Sell Digital Product',r'''<div class="hero"><h1>💼 Sell a Digital Product</h1><p>Upload a digital file and create a marketplace listing. New listings are unpublished until approved.</p></div><div class="card"><form method="post" enctype="multipart/form-data"><label>Product title</label><input name="title" maxlength="180" required placeholder="e.g. Grade 12 Mathematics Revision Guide"><label>Description</label><textarea name="description" maxlength="10000" required placeholder="Explain what the buyer receives..."></textarea><div class="grid"><div><label>Category</label><select name="category">{% for c in categories %}<option>{{ c }}</option>{% endfor %}</select></div><div><label>Price (ZMW)</label><input name="price" type="number" min="0" step="0.01" value="0" required></div></div><label>Contact phone</label><input name="contact_phone" placeholder="Phone number"><label>Email</label><input type="email" name="contact_email" placeholder="seller@example.com"><label>WhatsApp number</label><input name="whatsapp_number" placeholder="WhatsApp number"><label>Preferred contact</label><select name="preferred_contact"><option>KOJA Chat</option><option>WhatsApp</option><option>Phone</option><option>Email</option></select><div class="grid"><label><input type="checkbox" name="contact_phone_public"> Show phone publicly</label><label><input type="checkbox" name="contact_email_public"> Show email publicly</label><label><input type="checkbox" name="whatsapp_public"> Show WhatsApp publicly</label></div><div class="grid"><div><label>Location / Area</label><input name="location"></div><div><label>Town / City</label><input name="town"></div><div><label>Country</label><input name="country" value="Zambia"></div><div><label>Continent</label><select name="continent"><option>Africa</option><option>Asia</option><option>Europe</option><option>North America</option><option>South America</option><option>Oceania</option><option>Antarctica</option></select></div></div><label>Digital product file</label><input type="file" name="digital_file" required><label>Cover image (optional)</label><input type="file" name="cover" accept="image/jpeg,image/png,image/webp"><button class="btn" type="submit">📤 Submit Product</button></form><p class="small">Maximum upload size follows KOJA's 15 MB server limit.</p></div>''',categories=MARKETPLACE_CATEGORIES)

@app.route('/marketplace/my')
@login_required
def marketplace_my():
    uid=(current_user() or {}).get('id')
    products=db_select('koja_marketplace_products',{'seller_id':uid},order='created_at.desc',limit=100) or []
    orders=db_select('koja_marketplace_orders',{'seller_id':uid},order='created_at.desc',limit=100) or []
    purchases=db_select('koja_marketplace_orders',{'buyer_id':uid},order='created_at.desc',limit=100) or []
    ids={str(x.get('product_id')) for x in orders+purchases if x.get('product_id')}
    allp=db_select('koja_marketplace_products',{'id':'in.('+','.join(ids)+')'} if ids else {'id':'eq.__none__'},limit=200) or []
    pm={str(p.get('id')):p for p in allp}
    return render_page('My Marketplace',r'''<div class="hero"><h1>📦 My Marketplace</h1><div class="actions"><a class="btn" href="{{ url_for('marketplace_sell') }}">+ Sell Product</a><a class="btn secondary" href="{{ url_for('marketplace') }}">Browse Marketplace</a></div></div><div class="card"><h2>My Products</h2><table><tr><th>Product</th><th>Price</th><th>Status</th></tr>{% for p in products %}<tr><td>{{ p.title }}</td><td>{{ money(p.price,p.currency) if p.price|float>0 else 'FREE' }}</td><td>{{ 'Published' if p.is_published else 'Pending review' }}</td></tr>{% else %}<tr><td colspan="3">No products yet.</td></tr>{% endfor %}</table></div><div class="card"><h2>Sales / Orders</h2><table><tr><th>Product</th><th>Amount</th><th>Status</th><th>Actions</th></tr>{% for o in orders %}<tr><td>{{ pm.get(o.product_id,{}).get('title','Digital product') }}</td><td>{{ money(o.amount,o.currency) }}</td><td>{{ o.status }}</td><td>{% if o.status not in ['cancelled','refund_requested','refunded'] %}<form method="post" action="{{ url_for('marketplace_order_action',order_id=o.id,action='cancel') }}" style="display:inline"><button class="btn danger">Cancel</button></form><form method="post" action="{{ url_for('marketplace_order_action',order_id=o.id,action='refund') }}" style="display:inline"><button class="btn secondary">Refund</button></form>{% endif %}{% if o.status=='paid' %}<a class="btn" href="{{ url_for('marketplace_delivery',order_id=o.id) }}">🚚 Delivery</a>{% endif %}</td></tr>{% else %}<tr><td colspan="4">No orders yet.</td></tr>{% endfor %}</table></div><div class="card"><h2>My Purchases</h2><table><tr><th>Product</th><th>Amount</th><th>Status</th><th></th></tr>{% for o in purchases %}{% set pp=pm.get(o.product_id) %}<tr><td>{{ pp.title if pp else 'Digital product' }}</td><td>{{ money(o.amount,o.currency) }}</td><td>{{ o.status }}</td><td>{% if pp and o.status=='paid' %}<a class="btn success" href="{{ url_for('marketplace_download',product_id=pp.id) }}">Download</a><a class="btn" href="{{ url_for('marketplace_delivery',order_id=o.id) }}">🚚 Delivery</a>{% endif %}{% if o.status not in ['cancelled','refund_requested','refunded'] %}<form method="post" action="{{ url_for('marketplace_order_action',order_id=o.id,action='cancel') }}" style="display:inline"><button class="btn danger">Cancel</button></form><form method="post" action="{{ url_for('marketplace_order_action',order_id=o.id,action='refund') }}" style="display:inline"><button class="btn secondary">Refund</button></form>{% endif %}</td></tr>{% else %}<tr><td colspan="4">No purchases yet.</td></tr>{% endfor %}</table></div>''',products=products,orders=orders,purchases=purchases,pm=pm,money=marketplace_money)

@app.route("/professional-communication")
@login_required
def professional_communication():
    return render_page("Professional Communication", r"""
<div class="hero"><h2>👩‍💼 Professional Communication</h2><p>Choose a profession to access its dedicated communication space. Each profession has its own public room, public posts, and professional-to-client private communication.</p></div>
<div class="card"><div class="actions"><a class="btn" href="{{ url_for('professionals') }}">👥 Find Professionals</a><a class="btn secondary" href="{{ url_for('professional_register') }}">📝 Register as Professional</a></div></div>
<div class="grid">
{% for c in categories %}
<div class="card"><h3>{{ c }}</h3><p class="small">Dedicated {{ c }} communication.</p><div class="actions"><a class="btn" href="{{ url_for('professional_community', profession_slug=profession_slug(c)) }}">🌍 Public Communication</a><a class="btn secondary" href="{{ url_for('professional_public_post', profession_slug=profession_slug(c)) }}">📰 Public Posts</a></div></div>
{% endfor %}
</div>
""", categories=PROFESSIONAL_CATEGORIES)

@app.route("/professionals")
@login_required
def professionals():
    category = clean(request.args.get("category"))
    query = clean(request.args.get("q"))
    rows = db_select("service_providers", order="created_at.desc", limit=500)
    visible = []
    for x in rows:
        if str(x.get("provider_type") or "").lower() in {"driver", "doctor", "teacher", "tutor"}:
            continue
        status = str(x.get("approval_status") or x.get("verification_status") or "pending").lower()
        if status not in {"approved", "active", "verified"}:
            continue
        if x.get("is_active") is False:
            continue
        hay = " ".join(str(x.get(k) or "") for k in ("full_name","name","profession","specialization","qualification","service_area","address","bio","service_description")).lower()
        if category and category.lower() not in str(x.get("profession") or "").lower():
            continue
        if query and query.lower() not in hay:
            continue
        visible.append(x)
    return render_page("Professional Services", r"""
<div class="hero"><h2>👩‍💼 All Professional Services</h2><p>Find an approved professional, ask for advice or counselling, book a service, chat, or start a voice/video call.</p><div class="actions"><a class="btn" href="{{ url_for('professional_communication') }}">💬 Professional Communication</a></div></div>
<div class="card">
<form method="get" class="actions">
<input name="q" value="{{ query }}" placeholder="Search a profession, professional, service or qualification">
<select name="category"><option value="">All professions</option>{% for c in categories %}<option value="{{ c }}" {% if category==c %}selected{% endif %}>{{ c }}</option>{% endfor %}</select>
<button class="btn" type="submit">🔎 Search Profession</button>
<a class="btn secondary" href="{{ url_for('professional_register') }}">📝 Register as Professional</a>
</form>
<p class="small">Only administrator-approved professional profiles are shown publicly.</p>
</div>
<div class="grid">
{% for p in professionals %}
<div class="card">
<h3>{{ p.get('full_name') or p.get('name') or 'Professional' }}</h3>
<p><strong>Profession:</strong> {{ p.get('profession') or 'Professional Service' }}</p>
{% if p.get('specialization') %}<p><strong>Specialization:</strong> {{ p.get('specialization') }}</p>{% endif %}
{% if p.get('qualification') %}<p><strong>Qualification:</strong> {{ p.get('qualification') }}</p>{% endif %}
{% if p.get('experience_years') %}<p><strong>Experience:</strong> {{ p.get('experience_years') }} years</p>{% endif %}
{% if p.get('service_area') or p.get('address') %}<p><strong>Service area:</strong> {{ p.get('service_area') or p.get('address') }}</p>{% endif %}
{% if p.get('service_description') %}<p>{{ p.get('service_description') }}</p>{% elif p.get('bio') %}<p>{{ p.get('bio') }}</p>{% endif %}
{% if p.get('hourly_rate') %}<p><strong>Rate:</strong> {{ p.get('currency') or 'ZMW' }} {{ p.get('hourly_rate') }}</p>{% endif %}
<div class="actions">
<a class="btn" href="{{ url_for('professional_contact', provider_id=p.get('id')) }}">👤 Contact / Services</a>
<a class="btn secondary" href="{{ url_for('professional_community', profession_slug=profession_slug(p.get('profession') or 'Other Professional Service')) }}">🌍 Public Communication</a>
<a class="btn secondary" href="{{ url_for('book_professional', provider_id=p.get('id'), purpose='booking') }}">📅 Book</a>
<a class="btn secondary" href="{{ url_for('book_professional', provider_id=p.get('id'), purpose='advice') }}">💡 Ask Advice</a>
<a class="btn secondary" href="{{ url_for('book_professional', provider_id=p.get('id'), purpose='counselling') }}">🧠 Counselling</a>
</div>
</div>
{% else %}
<div class="card"><h3>No approved professionals found</h3><p>Search another profession or register as a professional.</p><a class="btn" href="{{ url_for('professional_register') }}">Register as Professional</a></div>
{% endfor %}
</div>
""", professionals=visible, categories=PROFESSIONAL_CATEGORIES, category=category, query=query)

@app.route("/professional/register", methods=["GET","POST"])
@login_required
def professional_register():
    user = current_user() or {}
    existing = first_row("service_providers", {"user_id": user.get("id"), "provider_type": "professional"})
    if request.method == "POST":
        profession = clean(request.form.get("profession"))
        if not profession:
            flash("Please select or enter your profession.", "danger")
            return redirect(url_for("professional_register"))
        payload = {
            "id": (existing or {}).get("id") or str(uuid.uuid4()), "user_id": user.get("id"), "provider_type": "professional",
            "full_name": clean(request.form.get("full_name")) or user.get("name") or user.get("full_name"),
            "name": clean(request.form.get("full_name")) or user.get("name") or user.get("full_name"),
            "phone": clean(request.form.get("phone")) or user.get("phone"), "email": clean(request.form.get("email")) or user.get("email"),
            "profession": profession, "specialization": clean(request.form.get("specialization")), "qualification": clean(request.form.get("qualification")),
            "experience_years": clean(request.form.get("experience_years")) or None, "service_area": clean(request.form.get("service_area")),
            "address": clean(request.form.get("address")), "bio": clean(request.form.get("bio")), "service_description": clean(request.form.get("service_description")),
            "hourly_rate": clean(request.form.get("hourly_rate")) or None, "currency": clean(request.form.get("currency")) or "ZMW",
            "is_available": False, "is_active": True, "verification_status": "pending", "approval_status": "pending", "created_at": utc_now(), "updated_at": utc_now()
        }
        if existing: data, error = db_update("service_providers", {"id": existing.get("id")}, payload)
        else: data, error = db_insert("service_providers", payload)
        if error:
            fallback = {k:v for k,v in payload.items() if k not in {"profession","specialization","qualification","experience_years","service_area","service_description","hourly_rate","currency","approval_status","updated_at"}}
            if existing: data, error = db_update("service_providers", {"id": existing.get("id")}, fallback)
            else: data, error = db_insert("service_providers", fallback)
        if error: flash("Professional registration failed: " + str(error)[:700], "danger")
        else: flash("Professional profile submitted for administrator approval.", "success")
        return redirect(url_for("professionals"))
    return render_page("Register as Professional", r"""
<div class="hero"><h2>📝 Register for Any Profession</h2><p>Register your professional service. Your profile becomes visible after administrator approval.</p></div>
<div class="card"><form method="post">
<label>Full Name</label><input name="full_name" value="{{ user.name or user.full_name or '' }}" required>
<label>Phone</label><input name="phone" value="{{ user.phone or '' }}" required>
<label>Email</label><input type="email" name="email" value="{{ user.email or '' }}">
<label>Profession</label><select name="profession" required><option value="">Select profession</option>{% for c in categories %}<option value="{{ c }}">{{ c }}</option>{% endfor %}</select>
<label>Specialization</label><input name="specialization" placeholder="Specialty or area of expertise">
<label>Qualification / Certification</label><input name="qualification" placeholder="Degree, licence, certificate or professional membership">
<label>Years of Experience</label><input name="experience_years" type="number" min="0" max="80" inputmode="numeric">
<label>Service Area</label><input name="service_area" placeholder="City, town, province or online">
<label>Address</label><input name="address">
<label>Services Offered</label><textarea name="service_description" placeholder="Describe the services you offer"></textarea>
<label>Professional Bio</label><textarea name="bio" placeholder="Experience, expertise and background"></textarea>
<label>Rate</label><input name="hourly_rate" type="number" min="0" step="0.01" placeholder="Optional">
<label>Currency</label><select name="currency"><option>ZMW</option><option>USD</option><option>ZAR</option></select>
<button type="submit">Submit Professional Registration</button>
</form></div>
""", categories=PROFESSIONAL_CATEGORIES, user=user)

@app.route("/professional/book/<provider_id>", methods=["GET", "POST"])
@login_required
def book_professional(provider_id):
    """Book an approved universal professional for a service, advice, or counselling."""
    user = current_user() or {}
    provider = first_row("service_providers", {"id": provider_id})
    if not provider or str(provider.get("provider_type") or "").lower() in {"driver", "doctor", "teacher", "tutor"}:
        abort(404)
    status = str(provider.get("approval_status") or provider.get("verification_status") or "pending").lower()
    if status not in {"approved", "active", "verified"}:
        return "This professional is not currently available for booking.", 403

    purpose = clean(request.args.get("purpose") or request.form.get("purpose") or "booking").lower()
    if purpose not in {"booking", "advice", "counselling"}:
        purpose = "booking"
    labels = {"booking": "Book Service", "advice": "Ask for Professional Advice", "counselling": "Request Counselling"}

    if request.method == "POST":
        payload = {
            "id": str(uuid.uuid4()),
            "client_id": user.get("id"),
            "provider_id": provider_id,
            "appointment_type": "professional_" + purpose,
            "appointment_date": request.form.get("appointment_date"),
            "start_time": request.form.get("start_time"),
            "end_time": request.form.get("end_time") or None,
            "location": clean(request.form.get("location")) or "Online",
            "status": "requested",
            "notes": clean(request.form.get("notes")),
            "created_at": utc_now(),
            "updated_at": utc_now(),
        }
        row, error = db_insert("appointments", payload)
        if error:
            flash("Request could not be submitted: " + str(error)[:700], "danger")
        else:
            flash("Professional request submitted successfully.", "success")
        return redirect(url_for("dashboard"))

    return render_page(labels[purpose], r"""
<div class="hero">
  <h2>{{ title }}</h2>
  <p><strong>{{ provider.get('full_name') or provider.get('name') or 'Professional' }}</strong> · {{ provider.get('profession') or 'Professional Service' }}</p>
  {% if provider.get('specialization') %}<p>{{ provider.get('specialization') }}</p>{% endif %}
</div>
<div class="card">
<form method="post">
<input type="hidden" name="purpose" value="{{ purpose }}">
<label>Date</label><input type="date" name="appointment_date" required>
<label>Start Time</label><input type="time" name="start_time" required>
<label>End Time</label><input type="time" name="end_time">
<label>Location / Online</label><input name="location" value="Online" placeholder="Office, home, clinic or online">
<label>Message / Details</label><textarea name="notes" required placeholder="Explain what you need from the professional"></textarea>
<button class="btn" type="submit">{{ title }}</button>
</form>
</div>
""", provider=provider, purpose=purpose, title=labels[purpose])

def professional_is_connected(provider):
    """Return True when an approved professional has an active recent presence."""
    if not provider:
        return False
    status = str(provider.get("approval_status") or provider.get("verification_status") or "pending").lower()
    if status not in {"approved", "active", "verified"}:
        return False
    if provider.get("is_available") is False:
        return False
    seen = provider.get("last_seen_at")
    if not seen:
        return False
    try:
        from datetime import datetime, timezone
        dt = datetime.fromisoformat(str(seen).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).total_seconds() <= 30
    except Exception:
        return False


@app.route("/api/professional/presence", methods=["POST"])
@login_required
def professional_presence():
    me = current_user() or {}
    provider = first_row("service_providers", {"user_id": me.get("id")})
    if not provider:
        return jsonify({"connected": False, "error": "Professional profile not found"}), 404
    data = request.get_json(silent=True) or {}
    online = bool(data.get("online", True))
    now = utc_now()
    updates = {"last_seen_at": now, "is_available": online, "updated_at": now}
    _, error = db_update("service_providers", {"id": provider.get("id")}, updates)
    if error:
        return jsonify({"connected": False, "error": str(error)[:400]}), 500
    return jsonify({"ok": True, "connected": online})


@app.route("/professional/contact/<provider_id>")
@login_required
def professional_contact(provider_id):
    provider = first_row("service_providers", {"id": provider_id})
    if not provider or str(provider.get("provider_type") or "").lower() in {"driver","doctor","teacher","tutor"}:
        return "Professional provider not found.", 404
    status = str(provider.get("approval_status") or provider.get("verification_status") or "pending").lower()
    connected = professional_is_connected(provider)
    if status not in {"approved","active","verified"} and str((current_user() or {}).get("id")) != str(provider.get("user_id")):
        return "This professional is not currently available.", 403
    return render_page("Contact Professional", r"""
<div class="hero"><h2>🤝 {{ provider.get('full_name') or provider.get('name') or 'Professional' }}</h2><p>{{ provider.get('profession') or 'Professional Service' }}{% if provider.get('specialization') %} · {{ provider.get('specialization') }}{% endif %}</p></div>
<div class="grid">
<div class="card"><h3>📅 Book</h3><p>Book this professional for a scheduled service.</p><a class="btn" href="{{ url_for('book_professional', provider_id=provider.id, purpose='booking') }}">Book Service</a></div>
<div class="card"><h3>💡 Professional Advice</h3><p>Ask a question and request advice from this profession.</p><a class="btn" href="{{ url_for('book_professional', provider_id=provider.id, purpose='advice') }}">Ask for Advice</a></div>
<div class="card"><h3>🧠 Counselling</h3><p>Request a counselling or consultation session where appropriate.</p><a class="btn" href="{{ url_for('book_professional', provider_id=provider.id, purpose='counselling') }}">Request Counselling</a></div>
<div class="card"><h3>🔒 Private Communication</h3><p>Direct communication with this professional.</p><a class="btn" href="{{ url_for('professional_chat', provider_id=provider.id) }}">💬 Private Chat</a><a class="btn secondary" href="{{ url_for('professional_call', provider_id=provider.id, mode='voice') }}">📞 Voice</a><a class="btn secondary" href="{{ url_for('professional_call', provider_id=provider.id, mode='video') }}">🎥 Video</a></div><div class="card"><h3>🌍 Public Communication</h3><p>Communicate with the wider {{ provider.get('profession') or 'professional' }} community.</p><a class="btn" href="{{ url_for('professional_community', profession_slug=profession_slug(provider.get('profession') or 'Other Professional Service')) }}">Open Public Room</a><a class="btn secondary" href="{{ url_for('professional_public_post', profession_slug=profession_slug(provider.get('profession') or 'Other Professional Service')) }}">Public Posts</a></div>
<div class="card"><h3>📞 Voice Call</h3>{% if connected %}<p>🟢 Connected — you can call this professional now.</p><a class="btn" href="{{ url_for('professional_call', provider_id=provider.id, mode='voice') }}">Start Voice Call</a>{% else %}<p>🔴 This professional is not connected right now.</p><button class="btn secondary" disabled>Voice Call Unavailable</button>{% endif %}</div>
<div class="card"><h3>🎥 Video Call</h3>{% if connected %}<p>🟢 Connected — you can start a video call now.</p><a class="btn" href="{{ url_for('professional_call', provider_id=provider.id, mode='video') }}">Start Video Call</a>{% else %}<p>🔴 This professional is not connected right now.</p><button class="btn secondary" disabled>Video Call Unavailable</button>{% endif %}</div><div class="card"><h3>⭐ Reviews</h3><p>Leave a rating and review after your service.</p><a class="btn secondary" href="{{ url_for('professional_review', provider_id=provider.id) }}">Review Professional</a></div><div class="card"><h3>📲 Incoming Calls</h3><p>Professionals can open their call inbox to receive calls.</p><a class="btn secondary" href="{{ url_for('professional_calls') }}">Open Call Inbox</a></div>
{% if provider.get('phone') %}<div class="card"><h3>📱 Phone</h3><a class="btn secondary" href="tel:{{ provider.get('phone') }}">Call {{ provider.get('phone') }}</a></div>{% endif %}
</div>
""", provider=provider, connected=connected)

@app.route("/professional/chat/<provider_id>")
@login_required
def professional_chat(provider_id):
    provider = first_row("service_providers", {"id": provider_id})
    if not provider: return "Professional provider not found.", 404
    me = current_user() or {}
    return render_page("Professional Chat", r"""
<div class="hero"><h2>💬 Chat with {{ provider.get('full_name') or provider.get('name') or 'Professional' }}</h2><p>{{ provider.get('profession') or 'Professional Service' }}</p></div>
<div class="card"><div id="messages" style="height:50vh;overflow:auto;border:1px solid var(--border);padding:12px;border-radius:10px"></div><form id="chatForm" class="actions" style="margin-top:10px"><input id="message" placeholder="Type your message..." required style="flex:1"><button class="btn" type="submit">Send</button></form><p id="chatStatus" class="small"></p></div>
<script>
const providerId={{ provider.id|tojson }}; const box=document.getElementById('messages');
async function loadMessages(){const r=await fetch('/api/professional/chat/'+providerId); if(!r.ok)return; const d=await r.json(); box.innerHTML=(d.messages||[]).map(m=>'<div style="margin:8px 0"><strong>'+esc(m.sender_name||'User')+'</strong><div>'+esc(m.message||'')+'</div><span class="small">'+esc(m.created_at||'')+'</span></div>').join(''); box.scrollTop=box.scrollHeight;}
function esc(v){return String(v??'').replace(/[&<>\"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#39;'}[c]));}
document.getElementById('chatForm').onsubmit=async e=>{e.preventDefault(); const msg=document.getElementById('message'); const r=await fetch('/api/professional/chat/'+providerId,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:msg.value})}); if(r.ok){msg.value='';loadMessages()}else document.getElementById('chatStatus').textContent='Message could not be sent.';};
loadMessages(); setInterval(loadMessages,2000);
</script>
""", provider=provider, me=me)

@app.route("/api/professional/chat/<provider_id>", methods=["GET","POST"])
@login_required
def professional_chat_api(provider_id):
    provider=first_row("service_providers", {"id":provider_id})
    if not provider: return jsonify({"error":"Provider not found"}),404
    me=current_user() or {}; me_id=str(me.get("id")); provider_user=str(provider.get("user_id") or "")
    if request.method=="POST":
        data=request.get_json(silent=True) or {}; message=clean(data.get("message"))
        if not message: return jsonify({"error":"Message required"}),400
        payload={"id":str(uuid.uuid4()),"sender_id":me_id,"receiver_id":provider_user,"provider_id":provider_id,"message":message,"created_at":utc_now()}
        row,error=db_insert("professional_messages",payload)
        if error: return jsonify({"error":str(error)[:500]}),500
        return jsonify({"ok":True,"message":row or payload})
    rows=db_select("professional_messages", order="created_at.asc", limit=500)
    relevant=[]
    for m in rows:
        a=str(m.get("sender_id") or ""); b=str(m.get("receiver_id") or "")
        if (a==me_id and b==provider_user and str(m.get("provider_id"))==str(provider_id)) or (a==provider_user and b==me_id and str(m.get("provider_id"))==str(provider_id)):
            relevant.append(m)
    for m in relevant:
        m["sender_name"] = "You" if str(m.get("sender_id"))==me_id else (provider.get("full_name") or provider.get("name") or "Professional")
    return jsonify({"messages":relevant})

@app.route("/professional/call/<provider_id>")
@login_required
def professional_call(provider_id):
    provider=first_row("service_providers", {"id":provider_id})
    if not provider: return "Professional provider not found.",404
    mode=clean(request.args.get("mode")).lower()
    if mode not in {"voice","video"}: mode="video"
    if not professional_is_connected(provider):
        return "This professional is not connected right now. Please try again when they are online.", 409
    return render_page("Professional Call", r"""
<div class="hero"><h2>{{ '🎥 Video Call' if mode=='video' else '📞 Voice Call' }}</h2><p>With {{ provider.get('full_name') or provider.get('name') or 'Professional' }} · {{ provider.get('profession') or 'Professional Service' }}</p></div>
<div class="card"><div id="incoming" style="display:none"></div><div id="callState">Preparing call…</div><div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:12px"><video id="local" autoplay muted playsinline style="width:100%;background:#111;border-radius:12px;{% if mode=='voice' %}display:none{% endif %}"></video><video id="remote" autoplay playsinline style="width:100%;background:#111;border-radius:12px;{% if mode=='voice' %}display:none{% endif %}"></video></div><audio id="remoteAudio" autoplay {% if mode!='voice' %}style="display:none"{% endif %}></audio><div class="actions" style="margin-top:14px"><button class="btn success" id="start">Start {{ mode.title() }} Call</button><button class="btn danger" id="hang">End Call</button><a class="btn secondary" href="{{ url_for('professional_contact', provider_id=provider.id) }}">Back</a></div><p class="small">Allow microphone/camera access. Both people must have an internet connection and keep this page open during the call.</p></div>
<script>
const providerId={{ provider.id|tojson }}, mode={{ mode|tojson }}; let callId=null, pc=null, poll=null; const uid={{ (user.get('id') if user else '')|tojson }};
const state=t=>document.getElementById('callState').textContent=t;
async function media(){return navigator.mediaDevices.getUserMedia({audio:true,video:mode==='video'})}
let callTimer=null;
function tellUnavailable(){const msg='This contact is not available. The call could not reach the professional. Please check your internet connection and try again later.'; state('🔴 '+msg); try{if('speechSynthesis' in window){speechSynthesis.cancel(); const u=new SpeechSynthesisUtterance(msg); u.lang='en-US'; speechSynthesis.speak(u)}}catch(e){}}
function failCall(){if(poll)clearInterval(poll); if(callTimer)clearTimeout(callTimer); if(pc){pc.getSenders().forEach(s=>{try{s.track&&s.track.stop()}catch(e){}}); pc.close(); pc=null} if(callId){fetch('/api/professional/call/'+callId+'/hangup',{method:'POST'}).catch(()=>{}); callId=null} tellUnavailable()}
async function startCall(){try{if(!navigator.onLine)throw Error('No internet connection'); const stream=await media(); document.getElementById('local').srcObject=stream; pc=new RTCPeerConnection({iceServers:[{urls:'stun:stun.l.google.com:19302'}]}); pc.onconnectionstatechange=()=>{if(pc && ['failed','disconnected'].includes(pc.connectionState)) failCall()}; stream.getTracks().forEach(t=>pc.addTrack(t,stream)); pc.ontrack=e=>{document.getElementById('remote').srcObject=e.streams[0];document.getElementById('remoteAudio').srcObject=e.streams[0]}; pc.onicecandidate=e=>{if(e.candidate && callId)fetch('/api/professional/call/'+callId+'/ice',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({candidate:e.candidate.toJSON(),side:'caller'})}).catch(()=>{})}; const offer=await pc.createOffer(); await pc.setLocalDescription(offer); const r=await fetch('/api/professional/call/'+providerId,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({mode,offer:offer.sdp})}); const d=await r.json(); if(!r.ok)throw Error(d.error||'Call failed'); callId=d.call_id; state('Calling professional…'); callTimer=setTimeout(failCall,30000); poll=setInterval(checkCall,1000)}catch(e){if(e.message&&(/internet|network|failed|available/i.test(e.message))) tellUnavailable(); else state('Could not start call: '+e.message)}}
async function checkCall(){if(!callId)return; try{const r=await fetch('/api/professional/call/'+callId,{cache:'no-store'}); if(!r.ok)throw Error('Network error'); const d=await r.json(); if(d.call && ['ended','declined','failed'].includes(d.call.status)){failCall();return} if(d.answer && pc && !pc.currentRemoteDescription){await pc.setRemoteDescription({type:'answer',sdp:d.answer}); if(callTimer)clearTimeout(callTimer); state('🟢 Connected');} for(const c of (d.callee_ice||[])){try{await pc.addIceCandidate(c)}catch(e){}}}catch(e){if(!navigator.onLine)failCall()}}
window.addEventListener('offline',()=>{if(callId)failCall()});
async function hang(){if(poll)clearInterval(poll); if(callTimer)clearTimeout(callTimer); if(pc){pc.getSenders().forEach(s=>{try{s.track&&s.track.stop()}catch(e){}});pc.close();pc=null} if(callId){await fetch('/api/professional/call/'+callId+'/hangup',{method:'POST'}).catch(()=>{});callId=null} state('Call ended')}
document.getElementById('start').onclick=startCall; document.getElementById('hang').onclick=hang;
</script>
""", provider=provider, mode=mode)

@app.route("/api/professional/call/<provider_id>", methods=["POST"])
@login_required
def professional_call_create(provider_id):
    if _rate_limited("call:" + (request.remote_addr or "unknown"), 10, 60):
        return jsonify({"error":"Too many call attempts. Please wait a moment and try again."}), 429
    provider=first_row("service_providers", {"id":provider_id}); me=current_user() or {}
    if not provider:return jsonify({"error":"Provider not found"}),404
    data=request.get_json(silent=True) or {}; mode=clean(data.get("mode")).lower(); offer=data.get("offer")
    if mode not in {"voice","video"} or not offer:return jsonify({"error":"Invalid call request"}),400
    if not professional_is_connected(provider): return jsonify({"error":"This professional is not connected right now."}),409
    payload={"id":str(uuid.uuid4()),"caller_id":me.get("id"),"callee_id":provider.get("user_id"),"provider_id":provider_id,"mode":mode,"status":"ringing","offer":offer,"created_at":utc_now()}
    row,error=db_insert("professional_calls",payload)
    if error:return jsonify({"error":str(error)[:500]}),500
    return jsonify({"ok":True,"call_id":payload["id"]})

@app.route("/api/professional/call/<call_id>")
@login_required
def professional_call_state(call_id):
    row=first_row("professional_calls", {"id":call_id}); me=current_user() or {}
    if not row:return jsonify({"error":"Call not found"}),404
    if str(me.get("id")) not in {str(row.get("caller_id")),str(row.get("callee_id"))}:return jsonify({"error":"Forbidden"}),403
    return jsonify({"call":row,"answer":row.get("answer"),"callee_ice":row.get("callee_ice") or []})

@app.route("/api/professional/call/<call_id>/ice", methods=["POST"])
@login_required
def professional_call_ice(call_id):
    row=first_row("professional_calls", {"id":call_id}); me=current_user() or {}; data=request.get_json(silent=True) or {}
    if not row:return jsonify({"error":"Call not found"}),404
    if str(me.get("id")) not in {str(row.get("caller_id")),str(row.get("callee_id"))}:return jsonify({"error":"Forbidden"}),403
    side=clean(data.get("side")); candidate=data.get("candidate")
    if side not in {"caller","callee"} or not candidate:return jsonify({"error":"Invalid candidate"}),400
    key="caller_ice" if side=="caller" else "callee_ice"; arr=row.get(key) or []; arr.append(candidate)
    _,error=db_update("professional_calls", {"id":call_id}, {key:arr})
    return (jsonify({"ok":True}) if not error else jsonify({"error":str(error)[:400]}), 200 if not error else 500)

@app.route("/api/professional/call/<call_id>/answer", methods=["POST"])
@login_required
def professional_call_answer(call_id):
    row=first_row("professional_calls", {"id":call_id}); me=current_user() or {}; data=request.get_json(silent=True) or {}
    if not row:return jsonify({"error":"Call not found"}),404
    if str(me.get("id"))!=str(row.get("callee_id")):return jsonify({"error":"Only the recipient can answer"}),403
    answer=data.get("answer")
    if not answer:return jsonify({"error":"Answer required"}),400
    _,error=db_update("professional_calls", {"id":call_id}, {"answer":answer,"status":"connected","answered_at":utc_now()})
    return (jsonify({"ok":True}) if not error else jsonify({"error":str(error)[:400]}),200 if not error else 500)

@app.route("/api/professional/call/<call_id>/hangup", methods=["POST"])
@login_required
def professional_call_hangup(call_id):
    row=first_row("professional_calls", {"id":call_id}); me=current_user() or {}
    if not row:return jsonify({"error":"Call not found"}),404
    if str(me.get("id")) not in {str(row.get("caller_id")),str(row.get("callee_id"))}:return jsonify({"error":"Forbidden"}),403
    _,error=db_update("professional_calls", {"id":call_id}, {"status":"ended","ended_at":utc_now()})
    return (jsonify({"ok":True}) if not error else jsonify({"error":str(error)[:400]}),200 if not error else 500)


@app.route("/professional/calls")
@login_required
def professional_calls():
    return render_page("Professional Calls", r"""
<div class="hero"><h2>📞 Professional Calls</h2><p>Incoming and active voice/video calls.</p></div>
<div id="calls" class="grid"><div class="card">Checking for calls…</div></div>
<script>
async function check(){const r=await fetch('/api/professional/incoming-calls'); if(!r.ok)return; const d=await r.json(); const box=document.getElementById('calls'); box.innerHTML=(d.calls||[]).map(c=>`<div class="card"><h3>Incoming ${c.mode==='video'?'🎥 Video':'📞 Voice'} Call</h3><p>From ${esc(c.caller_name||'User')}</p><a class="btn success" href="/professional/answer-call/${c.id}">Accept</a><button class="btn danger" onclick="rejectCall('${c.id}')">Reject</button></div>`).join('') || '<div class="card"><p>No incoming calls.</p></div>';}
function esc(v){return String(v??'').replace(/[&<>\"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#39;'}[c]));}
async function rejectCall(id){await fetch('/api/professional/call/'+id+'/hangup',{method:'POST'});check();} check();setInterval(check,2000);
async function presence(online=true){try{await fetch('/api/professional/presence',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({online})})}catch(e){}}
presence(true); setInterval(()=>presence(true),10000); window.addEventListener('pagehide',()=>navigator.sendBeacon('/api/professional/presence',new Blob([JSON.stringify({online:false})],{type:'application/json'})));
</script>
""")

@app.route("/api/professional/incoming-calls")
@login_required
def professional_incoming_calls():
    me=current_user() or {}; rows=db_select("professional_calls", order="created_at.desc", limit=100); out=[]
    for c in rows:
        if str(c.get("callee_id"))==str(me.get("id")) and str(c.get("status"))=="ringing":
            caller=first_row("profiles", {"id":c.get("caller_id")}) or {}
            c["caller_name"]=caller.get("full_name") or caller.get("name") or caller.get("email") or "User"
            out.append(c)
    return jsonify({"calls":out[:20]})

@app.route("/professional/answer-call/<call_id>")
@login_required
def professional_answer_call(call_id):
    call=first_row("professional_calls", {"id":call_id}); me=current_user() or {}
    if not call or str(call.get("callee_id"))!=str(me.get("id")):return "Call not found.",404
    provider=first_row("service_providers", {"id":call.get("provider_id")}) or {}
    return render_page("Answer Professional Call", r"""
<div class="hero"><h2>Incoming {{ '🎥 Video' if call.mode=='video' else '📞 Voice' }} Call</h2><p>Professional: {{ provider.get('full_name') or provider.get('name') or 'Professional' }}</p></div>
<div class="card"><button class="btn success" id="accept">Accept Call</button><button class="btn danger" id="decline">Decline</button><p id="state">Waiting…</p><video id="local" autoplay muted playsinline style="width:48%;background:#111;border-radius:12px;{% if call.mode=='voice' %}display:none{% endif %}"></video><video id="remote" autoplay playsinline style="width:48%;background:#111;border-radius:12px;{% if call.mode=='voice' %}display:none{% endif %}"></video><audio id="audio" autoplay {% if call.mode!='voice' %}style="display:none"{% endif %}></audio></div>
<script>
const id={{ call.id|tojson }}, mode={{ call.mode|tojson }};let pc=null,stream=null;const state=t=>document.getElementById('state').textContent=t;
async function accept(){try{stream=await navigator.mediaDevices.getUserMedia({audio:true,video:mode==='video'});document.getElementById('local').srcObject=stream;pc=new RTCPeerConnection({iceServers:[{urls:'stun:stun.l.google.com:19302'}]});stream.getTracks().forEach(t=>pc.addTrack(t,stream));pc.ontrack=e=>{document.getElementById('remote').srcObject=e.streams[0];document.getElementById('audio').srcObject=e.streams[0]};pc.onicecandidate=e=>{if(e.candidate)fetch('/api/professional/call/'+id+'/ice',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({candidate:e.candidate.toJSON(),side:'callee'})})};const r=await fetch('/api/professional/call/'+id);const d=await r.json();await pc.setRemoteDescription({type:'offer',sdp:d.call.offer});const answer=await pc.createAnswer();await pc.setLocalDescription(answer);await fetch('/api/professional/call/'+id+'/answer',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({answer:answer.sdp})});state('Connected');setInterval(async()=>{const q=await fetch('/api/professional/call/'+id);const x=await q.json();for(const c of (x.call.caller_ice||[])){try{await pc.addIceCandidate(c)}catch(e){}}},1000)}catch(e){state('Could not accept call: '+e.message)}}
document.getElementById('accept').onclick=accept;document.getElementById('decline').onclick=async()=>{await fetch('/api/professional/call/'+id+'/hangup',{method:'POST'});location.href='/professional/calls'};
</script>
""", call=call, provider=provider)

# ============================================================
# DRIVER REGISTRATION / PROFILE
# ============================================================

DRIVER_PROFILE_COLUMNS = (
    "id,provider_id,vehicle_type,vehicle_make,vehicle_model,"
    "vehicle_registration,driving_license_number,service_area,"
    "verification_status,created_at"
)


def get_driver_provider(user_id):
    """Return the driver's service provider; supports old/new schemas."""
    if not user_id:
        return None
    try:
        provider = first_row("service_providers", {"user_id": user_id, "provider_type": "driver"})
        if provider:
            return provider
    except Exception:
        pass
    try:
        return first_row("service_providers", {"user_id": user_id})
    except Exception:
        return None


def ensure_driver_provider(user):
    """Create/reuse a driver provider and tolerate legacy schemas."""
    if not user:
        return None, "User information is missing."
    user_id = user.get("id")
    if not user_id:
        return None, "User ID is missing."

    existing = get_driver_provider(user_id)
    if existing:
        return existing, None

    full_name = user.get("full_name") or user.get("name") or "Driver"
    payload = {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "provider_type": "driver",
        "full_name": full_name,
        "name": full_name,
        "phone": user.get("phone") or None,
        "email": user.get("email") or None,
        "verification_status": "pending",
        "is_available": False,
        "is_active": True
    }

    try:
        provider, error = db_insert("service_providers", payload)
    except Exception as exc:
        provider, error = None, str(exc)
    if not error:
        return provider or payload, None

    legacy = dict(payload)
    legacy.pop("provider_type", None)
    try:
        provider2, error2 = db_insert("service_providers", legacy)
    except Exception as exc:
        provider2, error2 = None, str(exc)
    if not error2:
        return provider2 or legacy, None
    return None, error

@app.route("/driver/register", methods=["GET", "POST"])
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

    return render_page("Driver Registration", r"""
<div class="hero"><h2>Driver Registration</h2>
<p>Complete your driver and vehicle information. A KOJA administrator must verify your registration before customers can request you.</p></div>
<div class="card">
<form method="post">
<label>Vehicle Type</label>
<select name="vehicle_type" required>
<option value="">Select vehicle type</option>
<option>Motorcycle</option><option>Car</option><option>Van</option><option>Pickup</option><option>Truck</option><option>Bicycle</option>
</select>
<label>Vehicle Make</label><input name="vehicle_make" value="{{ existing.get('vehicle_make','') if existing else '' }}" placeholder="Toyota, Honda, etc.">
<label>Vehicle Model</label><input name="vehicle_model" value="{{ existing.get('vehicle_model','') if existing else '' }}" placeholder="Model">
<label>Vehicle Registration</label><input name="vehicle_registration" value="{{ existing.get('vehicle_registration','') if existing else '' }}" required placeholder="ABC 1234">
<label>Driving Licence Number</label><input name="driving_license_number" value="{{ existing.get('driving_license_number','') if existing else '' }}" required>
<label>Service Area</label><input name="service_area" value="{{ existing.get('service_area','') if existing else '' }}" placeholder="e.g. Kitwe CBD, Chimwemwe">
{% if existing %}<p class="small">Current verification status: <strong>{{ existing.get('verification_status') or 'pending' }}</strong></p>{% endif %}
<button type="submit">Submit Driver Registration</button>
</form>
</div>
""", existing=existing)

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

    return render_page("Driver Dashboard", r"""
<div class="hero"><h2>Driver Dashboard</h2>
<p>{{ user.name }} — {{ profile.get('vehicle_type') or 'Vehicle' }} {{ profile.get('vehicle_registration') or '' }}</p>
<p>Verification: <strong>{{ profile.get('verification_status') or 'pending' }}</strong></p></div>
<div class="card"><h3>GPS / Availability</h3>
<p>Current status:
<span id="online-status" class="{{ 'online' if latest and latest.get('is_online') else 'offline' }}">
{{ 'ONLINE' if latest and latest.get('is_online') else 'OFFLINE' }}</span></p>
<div class="actions">
<a class="btn success" href="{{ url_for('tracking') }}{% if requests_rows %}?delivery_id={{ requests_rows[0].get('id') }}{% endif %}">Open GPS & Go Online</a>
<button class="btn danger" onclick="goOffline()">Go Offline</button>
</div><p id="offline-status" class="small"></p></div>
<div class="card"><h3>Delivery Requests / Jobs</h3>
{% for d in requests_rows %}<div class="card">
<strong>{{ d.get('tracking_code') }}</strong>
<p>{{ d.get('pickup_location') }} → {{ d.get('destination') }}</p>
<p>Status: <span class="badge">{{ d.get('status') or 'requested' }}</span></p>
<div class="actions">
{% if d.get('status') == 'requested' %}
<form method="post" action="{{ url_for('driver_delivery_action',delivery_id=d.get('id'),action='accept') }}"><button class="btn success">Accept</button></form>
<form method="post" action="{{ url_for('driver_delivery_action',delivery_id=d.get('id'),action='reject') }}"><button class="btn danger">Reject</button></form>
{% elif d.get('status') == 'accepted' %}<form method="post" action="{{ url_for('driver_delivery_action',delivery_id=d.get('id'),action='picked_up') }}"><button class="btn">Picked Up</button></form>
{% elif d.get('status') == 'picked_up' %}<form method="post" action="{{ url_for('driver_delivery_action',delivery_id=d.get('id'),action='in_transit') }}"><button class="btn">In Transit</button></form>
{% elif d.get('status') == 'in_transit' %}<form method="post" action="{{ url_for('driver_delivery_action',delivery_id=d.get('id'),action='delivered') }}"><button class="btn success">Delivered</button></form>{% endif %}
<a class="btn secondary" href="{{ url_for('track_delivery',tracking_code=d.get('tracking_code')) }}">Track Map</a><a class="btn secondary" href="{{ url_for('delivery_chat',delivery_id=d.get('id')) }}">💬 Chat</a><a class="btn secondary" href="{{ url_for('delivery_call',delivery_id=d.get('id'),mode='voice') }}">📞 Call</a>{% if d.get('status') in ['in_transit','delivered'] %}<a class="btn secondary" href="{{ url_for('delivery_proof',delivery_id=d.get('id')) }}">📦 Proof</a>{% endif %}
</div></div>
{% else %}<p>No delivery requests yet.</p>{% endfor %}
</div>
<script>
async function goOffline(){try{const r=await fetch('/api/driver/offline',{method:'POST'});const d=await r.json();document.getElementById('offline-status').textContent=d.message||'Driver is offline.';document.getElementById('online-status').textContent='OFFLINE';}catch(e){document.getElementById('offline-status').textContent='Unable to change status.'}}
</script>
""", profile=profile, latest=latest, requests_rows=requests_rows)

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
        try:
            _notify(delivery.get('customer_id') or delivery.get('user_id'),'Delivery status updated',f"Delivery {delivery.get('tracking_code')} is now {status}.",'delivery',delivery_id)
        except Exception:
            pass
        flash(f"Delivery status changed to {status}.", "success")
    return redirect(url_for("driver_dashboard"))

# DRIVER GPS
# ============================================================

@app.route("/tracking")
@login_required
def tracking():
    user=current_user()
    delivery_id = clean(request.args.get("delivery_id"))
    return render_page("Live GPS Tracking",r"""
<div class="hero"><h2>Live Driver GPS</h2><p>Allow browser location permission. Keep this page open while driving.</p></div>
<div class="card">
<label>Delivery ID (optional)</label>
<input id="delivery_id" value="{{ delivery_id or '' }}" placeholder="Assigned delivery ID (automatic when opened from a job)">
<div class="actions">
<button class="btn success" onclick="startTracking()">Go Online / Start GPS</button>
<button class="btn danger" onclick="stopTracking()">Stop GPS / Go Offline</button>
</div>
<p id="gps-status">GPS not started.</p>
<div id="map"></div>
</div>
<script>
let watchId=null,marker=null;
const map=L.map("map").setView([-13.9626,28.3228],6);
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",{maxZoom:19,attribution:"&copy; OpenStreetMap contributors"}).addTo(map);
function status(t){document.getElementById("gps-status").textContent=t}
function startTracking(){
 if(!navigator.geolocation){status("This browser does not support GPS.");return}
 status("Requesting GPS permission...");
 watchId=navigator.geolocation.watchPosition(sendPosition,gpsError,{enableHighAccuracy:true,maximumAge:3000,timeout:15000});
}
async function sendPosition(position){
 const c=position.coords, lat=c.latitude, lon=c.longitude;
 if(!marker){marker=L.marker([lat,lon]).addTo(map).bindPopup("Your live driver location");}
 else marker.setLatLng([lat,lon]);
 map.setView([lat,lon],16);
 const deliveryId=document.getElementById("delivery_id").value.trim();
 try{
  const r=await fetch("/api/driver/location",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({
   latitude:lat,longitude:lon,accuracy:c.accuracy,speed:c.speed,heading:c.heading,altitude:c.altitude,delivery_id:deliveryId||null
  })});
  const d=await r.json();
  status(d.ok?"ONLINE — GPS updated "+new Date().toLocaleTimeString():(d.message||"GPS update failed."));
 }catch(e){status("Network error while sending GPS.");}
}
function gpsError(e){
 if(e.code===1)status("Location permission denied. Allow location permission in browser settings.");
 else if(e.code===2)status("Device could not determine location.");
 else if(e.code===3)status("GPS timed out."); else status("GPS error.");
}
function stopTracking(){
 if(watchId!==null){navigator.geolocation.clearWatch(watchId);watchId=null;}
 fetch("/api/driver/offline",{method:"POST",headers:{"Content-Type":"application/json"}}).then(r=>r.json()).then(d=>status(d.message||"GPS sharing stopped.")).catch(()=>status("GPS stopped locally."));
}
</script>
""")

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
    return render_page("Nearby Drivers",r"""
<div class="hero"><h2>Nearby Delivery Drivers</h2><p>Share your pickup/shop location and KOJA will calculate distances to online drivers.</p></div>
<div class="card">
<div class="grid">
<div><label>Your Latitude</label><input id="lat" type="number" step="any" placeholder="-13.96"></div>
<div><label>Your Longitude</label><input id="lon" type="number" step="any" placeholder="28.32"></div>
</div>
<div class="actions">
<button class="btn" onclick="locateMe()">Use My Current Location</button>
<button class="btn success" onclick="findDrivers()">Find Nearby Drivers</button>
</div>
<p id="status" class="small"></p>
</div>
<div class="card"><div id="map"></div></div>
<div class="card"><h3>Available Drivers</h3><div id="driver-list">Enter your location and search.</div></div>
<script>
let map=L.map("map").setView([-13.9626,28.3228],6),me=null,markers=[];
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",{maxZoom:19,attribution:"&copy; OpenStreetMap contributors"}).addTo(map);
function locateMe(){
 if(!navigator.geolocation){document.getElementById("status").textContent="GPS is not supported.";return}
 document.getElementById("status").textContent="Requesting your location...";
 navigator.geolocation.getCurrentPosition(p=>{
  document.getElementById("lat").value=p.coords.latitude;
  document.getElementById("lon").value=p.coords.longitude;
  if(me)me.setLatLng([p.coords.latitude,p.coords.longitude]);else me=L.marker([p.coords.latitude,p.coords.longitude]).addTo(map).bindPopup("Your pickup/shop location");
  map.setView([p.coords.latitude,p.coords.longitude],14);
  document.getElementById("status").textContent="Location obtained.";
  findDrivers();
 },()=>document.getElementById("status").textContent="Location permission denied or unavailable.",{enableHighAccuracy:true,timeout:15000});
}
async function findDrivers(){
 const lat=parseFloat(document.getElementById("lat").value),lon=parseFloat(document.getElementById("lon").value);
 if(!Number.isFinite(lat)||!Number.isFinite(lon)){document.getElementById("status").textContent="Enter or obtain a valid location first.";return}
 document.getElementById("status").textContent="Searching for online drivers...";
 try{
  const r=await fetch(`/api/nearby-drivers?latitude=${encodeURIComponent(lat)}&longitude=${encodeURIComponent(lon)}&radius_km=50`);
  const d=await r.json();
  markers.forEach(m=>map.removeLayer(m));markers=[];
  const list=document.getElementById("driver-list");
  if(!d.ok){list.textContent=d.message||"Search failed.";return}
  if(me)me.setLatLng([lat,lon]);else me=L.marker([lat,lon]).addTo(map).bindPopup("Your pickup/shop location");
  if(!d.drivers.length){list.innerHTML="<p>No online drivers found within 50 km.</p>";document.getElementById("status").textContent="No nearby drivers are online.";return}
  list.innerHTML="";
  d.drivers.forEach(driver=>{
   const m=L.marker([driver.latitude,driver.longitude]).addTo(map).bindPopup(`<b>${escapeHtml(driver.name)}</b><br>${escapeHtml(driver.vehicle_type||"Vehicle")}<br>${driver.distance_km} km away`);
   markers.push(m);
   const div=document.createElement("div");div.className="card driver-card";
   div.innerHTML=`<h3>${escapeHtml(driver.name)}</h3><p class="online">ONLINE</p><p><b>Vehicle:</b> ${escapeHtml(driver.vehicle_type||"Not specified")} ${escapeHtml(driver.vehicle_registration||"")}</p><p><b>Distance:</b> ${driver.distance_km} km</p><p><b>Phone:</b> ${escapeHtml(driver.phone||"")}</p><div class="actions"><button class="btn success" onclick="requestDriver('${driver.driver_id}')">Request Delivery</button><button class="btn secondary" onclick="map.setView([${driver.latitude},${driver.longitude}],16)">View on Map</button></div>`;
   list.appendChild(div);
  });
  map.setView([lat,lon],13);
  document.getElementById("status").textContent=`Found ${d.drivers.length} online driver(s).`;
 }catch(e){document.getElementById("status").textContent="Unable to search drivers."}
}
function escapeHtml(s){return String(s??"").replace(/[&<>"']/g,m=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[m]))}
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
</script>
""")

@app.route("/api/nearby-drivers")
@login_required
def nearby_drivers():
    lat=safe_float(request.args.get("latitude"))
    lon=safe_float(request.args.get("longitude"))
    radius=safe_float(request.args.get("radius_km")) or 50
    radius=max(1,min(radius,200))

    if lat is None or lon is None or not (-90<=lat<=90) or not (-180<=lon<=180):
        return jsonify({"ok":False,"message":"Valid latitude and longitude are required."}),400

    if not table_exists("driver_locations"):
        return jsonify({"ok":False,"message":"The driver_locations table is not installed."}),503

    latest=latest_driver_locations()
    results=[]
    now=datetime.now(timezone.utc)

    for driver_id,loc in latest.items():
        if not loc.get("is_online"):
            continue
        dlat=safe_float(loc.get("latitude")); dlon=safe_float(loc.get("longitude"))
        if dlat is None or dlon is None:
            continue

        created=loc.get("created_at")
        # Do not show stale drivers older than 10 minutes.
        if created:
            try:
                dt=datetime.fromisoformat(str(created).replace("Z","+00:00"))
                if (now-dt).total_seconds()>600:
                    continue
            except Exception:
                pass

        distance=haversine_km(lat,lon,dlat,dlon)
        if distance>radius:
            continue

        profile=first_row("driver_profiles",{"provider_id":driver_id})
        provider=first_row("service_providers",{"id":driver_id}) or {}
        results.append({
            "driver_id":str(driver_id),
            "name":first_nonempty(provider.get("full_name"),provider.get("name"),"Driver"),
            "phone":first_nonempty(provider.get("phone")),
            "vehicle_type":first_nonempty(profile.get("vehicle_type") if profile else ""),
            "vehicle_registration":first_nonempty(profile.get("vehicle_registration") if profile else ""),
            "latitude":dlat,"longitude":dlon,
            "accuracy":loc.get("accuracy"),
            "distance_km":round(distance,2),
            "updated_at":loc.get("created_at")
        })

    results.sort(key=lambda x:x["distance_km"])
    return jsonify({"ok":True,"drivers":results})

# ============================================================
# DELIVERY REQUEST / TRACKING
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
        "pickup_address":clean(body.get("pickup_address") or body.get("pickup_location")),
        "destination":clean(body.get("destination")),
        "delivery_address":clean(body.get("delivery_address") or body.get("destination")),
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
            "pickup_address":payload["pickup_address"],
            "destination":payload["destination"],
            "delivery_address":payload["delivery_address"],
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
            "id":str(uuid.uuid4()),"customer_id":user["id"],"user_id":user["id"],
            "pickup_location":clean(request.form.get("pickup_location")),
            "pickup_address":clean(request.form.get("pickup_address") or request.form.get("pickup_location")),
            "destination":clean(request.form.get("destination")),
            "delivery_address":clean(request.form.get("delivery_address") or request.form.get("destination")),
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
    return render_page("Deliveries",r"""
<div class="hero"><h2>Delivery Service</h2><p>Use Nearby Drivers to see drivers around your shop/pickup location.</p><a class="btn success" href="{{ url_for('drivers') }}">Find Nearby Drivers</a></div>
<div class="card"><h2>Create Delivery Without Selecting Driver Yet</h2>
<form method="post">
<label>Pickup / Shop Location</label><input name="pickup_location" required>
<label>Destination</label><input name="destination" required>
<label>Recipient Name</label><input name="recipient_name" required>
<label>Recipient Phone</label><input name="recipient_phone" required>
<label>Package Description</label><textarea name="package_description"></textarea>
<label>Package Weight (kg)</label><input type="number" step="0.01" name="package_weight">
<label>Delivery Fee (ZMW)</label><input type="number" step="0.01" name="delivery_fee">
<label>Requested Date</label><input type="date" name="requested_date">
<label>Requested Time</label><input type="time" name="requested_time">
<label>Notes</label><textarea name="notes"></textarea>
<button type="submit">Create Delivery Request</button>
</form></div>
<div class="card"><h2>My Deliveries</h2>
{% for d in rows %}
<div class="card"><strong>{{ d.get("tracking_code") }}</strong>
<p>{{ d.get("pickup_location") }} → {{ d.get("destination") }}</p>
<p>Status: <span class="badge">{{ d.get("status") or "requested" }}</span></p>
<p>Driver: {{ d.get("driver_id") or "Not selected" }}</p>
<a class="btn" href="{{ url_for('track_delivery',tracking_code=d.get('tracking_code')) }}">Track Delivery</a>
{% if not d.get("driver_id") %}<a class="btn success" href="{{ url_for('drivers') }}">Find Driver</a>{% endif %}
</div>
{% else %}<p>No deliveries registered.</p>{% endfor %}
</div>
""",rows=rows)

@app.route("/track/<tracking_code>")
@login_required
def track_delivery(tracking_code):
    delivery=first_row("deliveries",{"tracking_code":tracking_code})
    if not delivery: abort(404)
    return render_page("Track Delivery",r"""
<div class="hero"><h2>Live Delivery Tracking</h2><p>Tracking code: <strong>{{ delivery.get("tracking_code") }}</strong></p></div>
<div class="card">
<p><strong>Pickup:</strong> {{ delivery.get("pickup_location") }}</p>
<p><strong>Destination:</strong> <span id="destination-text">{{ delivery.get("destination") }}</span></p>
<p><strong>Status:</strong> <span id="delivery-status">{{ delivery.get("status") }}</span></p>
<div class="grid">
<div class="stat"><div class="big" id="distance">—</div>Distance</div>
<div class="stat"><div class="big" id="eta">—</div>ETA</div>
<div class="stat"><div class="big" id="speed">—</div>Speed</div>
</div>
<div id="map"></div>
<p id="tracking-status" class="small">Connecting to driver's live GPS...</p>
<div class="actions">
<button class="btn secondary" onclick="centerDriver()">Center on Driver</button>
<button class="btn" onclick="fitRoute()">Show Route</button>
</div>
</div>
<script>
const trackingCode={{ delivery.get("tracking_code")|tojson }};
const destination={{ delivery.get("destination")|tojson }};
let map=L.map("map").setView([-13.9626,28.3228],6);
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",{maxZoom:19,attribution:"&copy; OpenStreetMap contributors"}).addTo(map);
let driverMarker=null,destinationMarker=null,routeLine=null,lastDriver=null,lastDestination=null,lastRouteAt=0;
let driverIcon=L.divIcon({className:"koja-driver-icon",html:"<div style='font-size:30px;line-height:30px;transform-origin:center;'>🚚</div>",iconSize:[32,32],iconAnchor:[16,16]});
function setText(id,t){const el=document.getElementById(id);if(el)el.textContent=t}
function centerDriver(){if(lastDriver)map.setView(lastDriver,17,{animate:true})}
function fitRoute(){const pts=[];if(lastDriver)pts.push(lastDriver);if(lastDestination)pts.push(lastDestination);if(pts.length===2)map.fitBounds(L.latLngBounds(pts),{padding:[40,40]})}
function km(m){return (m/1000).toFixed(1)+" km"}
function mins(sec){if(!Number.isFinite(sec))return "—";let m=Math.max(1,Math.round(sec/60));if(m<60)return m+" min";let h=Math.floor(m/60),r=m%60;return h+"h "+r+"m"}
async function geocodeDestination(){
 if(!destination)return;
 try{
  const url="https://nominatim.openstreetmap.org/search?format=jsonv2&limit=1&q="+encodeURIComponent(destination);
  const r=await fetch(url,{headers:{"Accept":"application/json"}}); const a=await r.json();
  if(!a.length){setText("tracking-status","Driver GPS connected. Destination could not be mapped automatically.");return}
  lastDestination=[parseFloat(a[0].lat),parseFloat(a[0].lon)];
  destinationMarker=L.marker(lastDestination).addTo(map).bindPopup("Delivery destination");
  setText("tracking-status","Destination mapped. Waiting for driver's live GPS...");
  await updateRoute(true);
 }catch(e){setText("tracking-status","Live GPS is available, but destination mapping failed.")}
}
async function updateRoute(force=false){
 if(!lastDriver||!lastDestination)return;
 if(!force && Date.now()-lastRouteAt<15000)return;
 lastRouteAt=Date.now();
 try{
  const a=lastDriver,b=lastDestination;
  const u=`/api/delivery/route?from_lat=${encodeURIComponent(a[0])}&from_lon=${encodeURIComponent(a[1])}&to_lat=${encodeURIComponent(b[0])}&to_lon=${encodeURIComponent(b[1])}`;
  const r=await fetch(u,{headers:{"Accept":"application/json"}});
  const d=await r.json();
  if(!d.ok||!d.geometry||!d.geometry.coordinates?.length)throw new Error(d.message||"No route");
  const coords=d.geometry.coordinates.map(x=>[x[1],x[0]]);
  if(routeLine)routeLine.setLatLngs(coords);else routeLine=L.polyline(coords,{weight:5,opacity:.8}).addTo(map);
  setText("distance",km(Number(d.distance_m)));
  setText("eta",mins(Number(d.duration_s)));
  fitRoute();
 }catch(e){
  const R=6371,la1=a[0]*Math.PI/180,la2=b[0]*Math.PI/180,dla=(b[0]-a[0])*Math.PI/180,dlo=(b[1]-a[1])*Math.PI/180;
  const x=Math.sin(dla/2)**2+Math.cos(la1)*Math.cos(la2)*Math.sin(dlo/2)**2;
  const straight=2*R*Math.atan2(Math.sqrt(x),Math.sqrt(1-x));
  setText("distance",straight.toFixed(1)+" km");
 }
}
async function load(){
 try{
  const r=await fetch("/api/delivery/"+encodeURIComponent(trackingCode)+"/location");
  const d=await r.json();
  setText("delivery-status",d.status||"");
  if(!d.ok){setText("tracking-status",d.message||"No driver GPS available yet.");return}
  const p=[Number(d.latitude),Number(d.longitude)];
  if(!Number.isFinite(p[0])||!Number.isFinite(p[1]))return;
  lastDriver=p;
  if(!driverMarker){driverMarker=L.marker(p,{icon:driverIcon}).addTo(map).bindPopup("Live driver location");map.setView(p,15)}
  else driverMarker.setLatLng(p);
  const heading=Number(d.heading);
  const node=driverMarker.getElement()?.querySelector("div");
  if(node&&Number.isFinite(heading))node.style.transform="rotate("+heading+"deg)";
  if(Number.isFinite(Number(d.speed)) && Number(d.speed)>=0)setText("speed",(Number(d.speed)*3.6).toFixed(0)+" km/h");else setText("speed","—");
  const age=d.age_seconds!=null?Math.max(0,Math.round(d.age_seconds)):null;
  setText("tracking-status","LIVE — driver's GPS updated "+(age===null?"now":age+"s ago")+". Accuracy: "+(d.accuracy?Math.round(d.accuracy)+" m":"—"));
  await updateRoute(false);
 }catch(e){setText("tracking-status","Network connection lost. Retrying live GPS...")}
}
geocodeDestination();
load();
setInterval(load,5000);
setInterval(()=>updateRoute(true),15000);
</script>
""",delivery=delivery)

@app.route("/api/delivery/route", methods=["GET"])
@login_required
def delivery_route():
    """Return a road route between two WGS84 points using OSRM."""
    try:
        lat1=safe_float(request.args.get("from_lat")); lon1=safe_float(request.args.get("from_lon"))
        lat2=safe_float(request.args.get("to_lat")); lon2=safe_float(request.args.get("to_lon"))
        vals=(lat1,lon1,lat2,lon2)
        if any(v is None for v in vals):
            return jsonify({"ok":False,"message":"Four valid coordinates are required."}),400
        if not (-90<=lat1<=90 and -180<=lon1<=180 and -90<=lat2<=90 and -180<=lon2<=180):
            return jsonify({"ok":False,"message":"Coordinates are out of range."}),400
        url=f"https://router.project-osrm.org/route/v1/driving/{lon1},{lat1};{lon2},{lat2}"
        r=requests.get(url,params={"overview":"full","geometries":"geojson","steps":"false"},timeout=12)
        r.raise_for_status(); data=r.json()
        if not data.get("routes"):
            return jsonify({"ok":False,"message":"No road route found."}),404
        route=data["routes"][0]
        return jsonify({"ok":True,"distance_m":route.get("distance",0),"duration_s":route.get("duration",0),"geometry":route.get("geometry",{} )})
    except requests.RequestException:
        return jsonify({"ok":False,"message":"Routing service is temporarily unavailable."}),503
    except Exception as exc:
        logger.exception("Route lookup failed")
        return jsonify({"ok":False,"message":"Could not calculate route.","error":str(exc)[:200]}),500

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
    return render_page("Provider Location",r"""
<div class="hero"><h2>{{ provider_type|title }} Location</h2><p>Latest GPS position shared by this provider.</p></div>
<div class="card"><div id="map"></div><p id="status">Loading provider location...</p></div>
<script>
const providerId={{ provider_id|tojson }},map=L.map("map").setView([-13.9626,28.3228],6);
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",{maxZoom:19,attribution:"&copy; OpenStreetMap contributors"}).addTo(map);
let marker=null;
async function update(){
 try{
  const r=await fetch("/api/provider/"+encodeURIComponent(providerId)+"/location"),d=await r.json();
  if(!d.ok){document.getElementById("status").textContent=d.message||"No location available.";return}
  const p=[d.latitude,d.longitude];
  if(!marker){marker=L.marker(p).addTo(map).bindPopup("Provider location");map.setView(p,15)}else marker.setLatLng(p);
  document.getElementById("status").textContent="Last update: "+d.updated_at;
 }catch(e){document.getElementById("status").textContent="Unable to load GPS position."}
}
update();setInterval(update,10000);
</script>
""",provider_id=provider_id,provider_type=provider_type)

@app.route("/api/provider/<provider_id>/location")
@login_required
def provider_location(provider_id):
    rows=db_select("driver_locations",filters={"driver_id":provider_id},order="created_at.desc",limit=1)
    if not rows:
        return jsonify({"ok":False,"message":"This provider has not shared a GPS location."})
    loc=rows[0]
    return jsonify({"ok":True,"latitude":loc.get("latitude"),"longitude":loc.get("longitude"),"accuracy":loc.get("accuracy"),"updated_at":loc.get("created_at")})

# ============================================================
# GOOGLE SEARCH & DISTRIBUTION
# ============================================================

PUBLIC_INDEX_ROUTES = [
    "/",
    "/research",
    "/research/notes",
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

    return render_page("Google Search & Distribution", r"""
<div class="hero">
  <h2>🔎 Google Search & Distribution</h2>
  <p>Real Google Search Console controls and performance data for KOJA AFRICA.</p>
  <div class="actions">
    <a class="btn" href="https://search.google.com/search-console" target="_blank" rel="noopener">Open Google Search Console</a>
    <a class="btn secondary" href="{{ url_for('sitemap_xml') }}" target="_blank">View Sitemap</a>
    <a class="btn secondary" href="{{ url_for('robots_txt') }}" target="_blank">View robots.txt</a>
  </div>
</div>

<div class="grid">
  <div class="stat"><div class="big">{{ 'CONNECTED' if query_report.connected else 'NOT CONNECTED' }}</div>Search Console API</div>
  <div class="stat"><div class="big">{{ indexed_candidates|length }}</div>Public sitemap URLs</div>
  <div class="stat"><div class="big">{{ query_report.rows|length if query_report.connected else '—' }}</div>Search queries</div>
  <div class="stat"><div class="big">{{ days }}</div>Days</div>
</div>

<div class="card">
<h3>📊 Search performance</h3>
<p class="small">{{ query_report.message }}</p>
{% if query_report.connected %}
<div class="grid">
{% set total_clicks = query_report.rows|sum(attribute='clicks') %}
{% set total_impressions = query_report.rows|sum(attribute='impressions') %}
<div class="stat"><div class="big">{{ '%.0f'|format(total_clicks) }}</div>Clicks in returned query rows</div>
<div class="stat"><div class="big">{{ '%.0f'|format(total_impressions) }}</div>Impressions in returned query rows</div>
<div class="stat"><div class="big">{{ daily_report.rows|length }}</div>Days with data</div>
</div>
{% else %}
<p>Connect the property to show real clicks, impressions, CTR and average position. Google requires authorized access to the Search Console property for the Search Analytics API.</p>
{% endif %}
</div>

{% if query_report.connected %}
<div class="card">
<div class="actions"><h3 style="margin-right:auto">Top Search Queries</h3><a class="btn secondary" href="{{ url_for('admin_search_distribution',days=7) }}">7 days</a><a class="btn secondary" href="{{ url_for('admin_search_distribution',days=28) }}">28 days</a><a class="btn secondary" href="{{ url_for('admin_search_distribution',days=90) }}">90 days</a></div>
<table><tr><th>Query</th><th>Clicks</th><th>Impressions</th><th>CTR</th><th>Avg. position</th></tr>
{% for r in query_report.rows %}<tr><td>{{ r.key }}</td><td>{{ r.clicks }}</td><td>{{ r.impressions }}</td><td>{{ r.ctr }}%</td><td>{{ r.position }}</td></tr>{% else %}<tr><td colspan="5">No search-query data is available.</td></tr>{% endfor %}</table>
</div>
<div class="card"><h3>Top Pages from Google Search</h3>
<table><tr><th>Page</th><th>Clicks</th><th>Impressions</th><th>CTR</th><th>Avg. position</th></tr>
{% for r in page_report.rows %}<tr><td>{{ r.key }}</td><td>{{ r.clicks }}</td><td>{{ r.impressions }}</td><td>{{ r.ctr }}%</td><td>{{ r.position }}</td></tr>{% else %}<tr><td colspan="5">No page data is available.</td></tr>{% endfor %}</table></div>
<div class="card"><h3>Daily Search Performance</h3><table><tr><th>Date</th><th>Clicks</th><th>Impressions</th><th>CTR</th><th>Avg. position</th></tr>
{% for r in daily_report.rows %}<tr><td>{{ r.key }}</td><td>{{ r.clicks }}</td><td>{{ r.impressions }}</td><td>{{ r.ctr }}%</td><td>{{ r.position }}</td></tr>{% endfor %}</table></div>
{% endif %}

<div class="card">
<h3>🔍 URL Inspection</h3>
<p>Enter a KOJA URL and send it to Google's real URL Inspection API.</p>
<form method="post">
<input type="hidden" name="action" value="inspect">
<input name="inspect_url" value="{{ request.form.get('inspect_url', SITE_URL + '/') }}" placeholder="https://koja-africa.onrender.com/">
<button class="btn" type="submit">Inspect URL</button>
</form>
{% if inspect_result %}
<div class="alert"><strong>{{ inspect_result.message }}</strong></div>
{% if inspect_result.ok %}<table><tr><th>Verdict</th><td>{{ inspect_result.verdict }}</td></tr><tr><th>Coverage</th><td>{{ inspect_result.coverage }}</td></tr><tr><th>Indexing</th><td>{{ inspect_result.indexing }}</td></tr><tr><th>Google canonical</th><td>{{ inspect_result.canonical }}</td></tr><tr><th>Last crawl</th><td>{{ inspect_result.last_crawl }}</td></tr><tr><th>Robots</th><td>{{ inspect_result.robots }}</td></tr></table>{% endif %}
{% endif %}
</div>

<div class="card">
<h3>🗺️ Sitemap distribution</h3>
<p>Your sitemap: <a href="{{ url_for('sitemap_xml') }}" target="_blank">{{ SITE_URL }}/sitemap.xml</a></p>
<form method="post"><input type="hidden" name="action" value="submit_sitemap"><button class="btn success" type="submit">Submit sitemap to Google</button></form>
{% if submit_message %}<div class="alert">{{ submit_message[1] }}</div>{% endif %}
{% if sitemap_report.ok %}<h4>Sitemaps known to Google</h4><table><tr><th>Path</th><th>Last submitted</th><th>Last downloaded</th><th>Warnings</th><th>Errors</th></tr>{% for sm in sitemap_report.sitemaps %}<tr><td>{{ sm.path }}</td><td>{{ sm.lastSubmitted }}</td><td>{{ sm.lastDownloaded }}</td><td>{{ sm.warnings }}</td><td>{{ sm.errors }}</td></tr>{% else %}<tr><td colspan="5">No sitemap is currently listed by the API.</td></tr>{% endfor %}</table>{% else %}<p class="small">{{ sitemap_report.message }}</p>{% endif %}
</div>

<div class="card"><h3>🚀 Public distribution</h3><table><tr><th>URL</th><th>Status</th></tr>{% for u in indexed_candidates %}<tr><td><a href="{{ SITE_URL }}{{ u }}" target="_blank">{{ SITE_URL }}{{ u }}</a></td><td>Included in sitemap</td></tr>{% endfor %}</table></div>

<div class="card"><h3>⚙️ One-time Google connection</h3><ol><li>Create/select a Google Cloud project.</li><li>Enable the Search Console API.</li><li>Create a service account and download its JSON credentials.</li><li>Add that service-account email as an owner/full user of the verified <strong>{{ GSC_SITE_URL }}</strong> Search Console property.</li><li>Put the JSON contents into the Render environment variable <code>GSC_SERVICE_ACCOUNT_JSON</code>.</li><li>Set <code>GSC_SITE_URL=https://koja-africa.onrender.com/</code>.</li><li>Redeploy KOJA AFRICA.</li></ol><p class="small">The credentials stay server-side; never put the service-account JSON in HTML or browser JavaScript.</p></div>
""", query_report=query_report, page_report=page_report, daily_report=daily_report, days=days, indexed_candidates=indexed_candidates, inspect_result=inspect_result, submit_message=submit_message, sitemap_report=sitemap_report, SITE_URL=SITE_URL, GSC_SITE_URL=GSC_SITE_URL)


@app.route("/robots.txt")
def robots_txt():
    lines = [
        "User-agent: *",
        "Allow: /",
        "Disallow: /admin",
        "Disallow: /login",
        "Disallow: /register",
        "Disallow: /dashboard",
        "Disallow: /settings",
        "Disallow: /services",
        "Disallow: /api/",
        f"Sitemap: {SITE_URL}/sitemap.xml",
    ]
    return ("\n".join(lines) + "\n", 200, {"Content-Type": "text/plain; charset=utf-8"})


@app.route("/sitemap.xml")
def sitemap_xml():
    urls = []
    lastmod = datetime.now(timezone.utc).date().isoformat()
    for route in PUBLIC_INDEX_ROUTES:
        urls.append(f"<url><loc>{SITE_URL}{route}</loc><lastmod>{lastmod}</lastmod><changefreq>weekly</changefreq><priority>{'1.0' if route == '/' else '0.7'}</priority></url>")
    xml = '<?xml version="1.0" encoding="UTF-8"?>' + '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + ''.join(urls) + '</urlset>'
    return (xml, 200, {"Content-Type": "application/xml; charset=utf-8"})

# ============================================================
# ADMIN
# ============================================================

@app.route('/admin/marketplace', methods=['GET','POST'])
@login_required
def admin_marketplace():
    if not (current_user() or {}).get('is_admin'): abort(403)
    if request.method=='POST':
        action=clean(request.form.get('action')); item_id=clean(request.form.get('item_id'))
        if action in ('publish','unpublish'):
            db_update('koja_marketplace_products',{'id':item_id},{'is_published':action=='publish','updated_at':utc_now()})
            flash('Marketplace product status updated.','success')
        elif action=='paid':
            db_update('koja_marketplace_orders',{'id':item_id},{'status':'paid','updated_at':utc_now()})
            flash('Order marked paid. Verify the payment independently before doing this.','success')
        elif action=='cancel':
            db_update('koja_marketplace_orders',{'id':item_id},{'status':'cancelled','updated_at':utc_now()})
            flash('Order cancelled.','success')
        return redirect(url_for('admin_marketplace'))
    products=db_select('koja_marketplace_products',order='created_at.desc',limit=200) or []
    orders=db_select('koja_marketplace_orders',order='created_at.desc',limit=200) or []
    return render_page('Marketplace Admin',r'''<div class="hero"><h1>🛡️ Marketplace Admin</h1><p>Review products and manage marketplace orders.</p></div><div class="card"><h2>Products</h2><table><tr><th>Product</th><th>Price</th><th>Seller</th><th>Status</th><th>Action</th></tr>{% for p in products %}<tr><td>{{ p.title }}</td><td>{{ money(p.price,p.currency) }}</td><td>{{ seller_names.get(p.seller_id,'KOJA Seller') }}</td><td>{{ 'Published' if p.is_published else 'Pending' }}</td><td><form method="post" style="display:inline"><input type="hidden" name="item_id" value="{{ p.id }}"><button class="btn {{ 'warning' if p.is_published else 'success' }}" name="action" value="{{ 'unpublish' if p.is_published else 'publish' }}" type="submit">{{ 'Unpublish' if p.is_published else 'Publish' }}</button></form></td></tr>{% else %}<tr><td colspan="5">No products.</td></tr>{% endfor %}</table></div><div class="card"><h2>Orders</h2><table><tr><th>Product</th><th>Amount</th><th>Status</th><th>Action</th></tr>{% for o in orders %}<tr><td>{{ product_names.get(o.product_id,'Digital product') }}</td><td>{{ money(o.amount,o.currency) }}</td><td>{{ o.status }}</td><td>{% if o.status=='pending' %}<form method="post"><input type="hidden" name="item_id" value="{{ o.id }}"><button class="btn success" name="action" value="paid" type="submit">Mark Paid</button><button class="btn danger" name="action" value="cancel" type="submit">Cancel</button></form>{% endif %}</td></tr>{% else %}<tr><td colspan="4">No orders.</td></tr>{% endfor %}</table></div>''',products=products,orders=orders,seller_names={str(p.get('seller_id')):marketplace_seller_name(p.get('seller_id')) for p in products},product_names={str(p.get('id')):p.get('title') for p in products},money=marketplace_money)

@app.route("/admin")
@admin_required
def admin():
    tables=["profiles","questions","assignments","documents","document_records","service_providers","doctor_profiles","teacher_profiles","driver_profiles","driver_locations","deliveries","appointments","cv_records","activity_logs"]
    counts={}
    for table in tables:
        counts[table]=len(db_select(table,limit=1000))
    return render_page("Admin Dashboard",r"""
<div class="hero"><h2>KOJA Administrator</h2><p>System management dashboard.</p></div>
<div class="grid">{% for name,count in counts.items() %}<div class="stat"><div class="big">{{ count }}</div>{{ name }}</div>{% endfor %}</div>
<div class="card"><h3>Management</h3>
<div class="actions">
<a class="btn" href="{{ url_for('admin_users') }}">Users</a>
<a class="btn success" href="{{ url_for('admin_assignments') }}">📚 Assignments & Answers</a>
<a class="btn success" href="{{ url_for('admin_approvals') }}">✅ Approval Centre</a>
<a class="btn" href="{{ url_for('admin_email_settings') }}">📧 Email Management</a>
<a class="btn" href="{{ url_for('admin_drivers') }}">Drivers</a>
<a class="btn" href="{{ url_for('admin_deliveries') }}">Deliveries</a>
<a class="btn success" href="{{ url_for('admin_live_tracking') }}">🚚 Live GPS Tracking</a>
<a class="btn" href="{{ url_for('admin_appointments') }}">Appointments</a>
<a class="btn success" href="{{ url_for('admin_search_distribution') }}">🔎 Google Search & Distribution</a>
</div></div>
""",counts=counts)

@app.route("/admin/users")
@admin_required
def admin_users():
    rows=db_select("profiles",order="created_at.desc",limit=300)
    return render_page("Admin Users",r"""
<div class="card"><h2>Users</h2><table><tr><th>Name</th><th>Email</th><th>Phone</th><th>Role</th><th>Admin</th></tr>
{% for u in rows %}<tr><td>{{ u.get("full_name") or u.get("name") }}</td><td>{{ u.get("email") }}</td><td>{{ u.get("phone") or "" }}</td><td>{{ u.get("role") or "" }}</td><td>{{ "Yes" if u.get("is_admin") else "No" }}</td></tr>{% endfor %}
</table></div>
""",rows=rows)

@app.route("/admin/assignments", methods=["GET"])
@admin_required
def admin_assignments():
    rows = db_select("assignments", order="created_at.desc", limit=300)
    enriched = []
    for item in rows:
        email, profile = get_assignment_recipient(item)
        copy = dict(item)
        copy["recipient_email"] = email
        copy["recipient_name"] = (profile or {}).get("full_name") or (profile or {}).get("name") or "User"
        enriched.append(copy)
    return render_page("Admin Assignments", r"""
<div class="hero"><h2>📚 Assignment Answer Management</h2>
<p>Write an answer, upload the answer PDF, save it to the specific assignment owner, and send the PDF by email.</p></div>
<div class="card"><p><strong>Email status:</strong> {{ "Configured" if email_configured else "Not configured" }} · <a class="btn secondary" href="{{ url_for('admin_email_settings') }}">Manage Email</a></p>
<p class="small">For Gmail, use a Google App Password in the server environment. Never place the password in this page.</p></div>
{% for item in rows %}
<div class="card">
<h3>{{ item.get("title") or "Assignment" }}</h3>
<p>{{ item.get("description") or "" }}</p>
<p class="small"><strong>Owner/Sender:</strong> {{ item.get("recipient_name") }} · <strong>Email:</strong> {{ item.get("recipient_email") or "No email found" }} · <strong>Tracking:</strong> {{ item.get("tracking_code") or "—" }}</p>
<p><span class="badge">{{ item.get("status") or "Submitted" }}</span>{% if item.get("answer_file_path") %} <span class="badge">PDF Answer Uploaded</span>{% endif %}</p>
<div class="actions">
<a class="btn secondary" href="{{ url_for('assignment_question_view', assignment_id=item.get('id')) }}">📖 Read Question</a>
<a class="btn secondary" href="{{ url_for('assignment_question_download', assignment_id=item.get('id')) }}">⬇️ Download Question</a>
{% if item.get("file_path") %}<a class="btn" href="{{ url_for('assignment_file', assignment_id=item.get('id'), kind='original') }}">⬇️ Download Assignment</a>{% endif %}
<a class="btn" href="{{ url_for('admin_assignment_answer', assignment_id=item.get('id')) }}">✍️ Read Question / Write Answer</a>
{% if item.get("answer_file_path") %}<a class="btn success" href="{{ url_for('assignment_file', assignment_id=item.get('id'), kind='answer') }}">⬇️ View Answer PDF</a>{% endif %}
</div>
</div>
{% else %}<div class="card"><p>No assignments found.</p></div>{% endfor %}
""", rows=enriched, email_configured=email_configured())

@app.route("/admin/assignments/<assignment_id>/answer", methods=["GET", "POST"])
@admin_required
def admin_assignment_answer(assignment_id):
    item = first_row("assignments", {"id": assignment_id})
    if not item:
        return "Assignment not found.", 404
    recipient_email, recipient = get_assignment_recipient(item)
    if request.method == "POST":
        answer_text = clean(request.form.get("answer"))
        pdf = request.files.get("answer_pdf")
        if not answer_text and not (pdf and pdf.filename):
            flash("Write an answer or upload an answer PDF.", "danger")
            return redirect(url_for("admin_assignment_answer", assignment_id=assignment_id))

        updates = {
            "answer": answer_text or item.get("answer") or None,
            "answered_by": current_user().get("id"),
            "answered_at": utc_now(),
            "status": "answered",
        }
        if pdf and pdf.filename:
            if not pdf.filename.lower().endswith(".pdf"):
                flash("The answer file must be a PDF.", "danger")
                return redirect(url_for("admin_assignment_answer", assignment_id=assignment_id))
            uploaded, error = upload_storage(pdf, "assignment-answers")
            if error:
                flash(f"PDF upload failed: {error}", "danger")
                return redirect(url_for("admin_assignment_answer", assignment_id=assignment_id))
            updates.update({
                "answer_file_name": uploaded["file_name"],
                "answer_file_path": uploaded["path"],
                "answer_file_url": uploaded["url"],
            })
        row, error = db_update("assignments", {"id": assignment_id}, updates)
        if error:
            flash("Answer could not be saved. Check the assignments table columns.", "danger")
        else:
            flash("Answer saved successfully. The PDF is linked to the specific assignment owner.", "success")
            log_activity("assignment_answered", f"Admin answered assignment {item.get('tracking_code') or assignment_id}.")
        return redirect(url_for("admin_assignment_answer", assignment_id=assignment_id))

    item = first_row("assignments", {"id": assignment_id}) or item
    return render_page("Write Assignment Answer", r"""
<div class="hero"><h2>✍️ Answer Assignment</h2><p>{{ item.get("title") or "Assignment" }} · {{ item.get("tracking_code") or "No tracking code" }}</p></div>
<div class="card"><p><strong>Specific user:</strong> {{ recipient_name }}</p><p><strong>Email:</strong> {{ recipient_email or "No email found" }}</p><p><strong>Current status:</strong> <span class="badge">{{ item.get("status") or "submitted" }}</span></p><p class="small">The answer belongs only to this assignment owner.</p></div>
<div class="card"><h3>📖 Read Uploaded Assignment Question</h3><p><strong>{{ item.get("title") or "Assignment" }}</strong></p><div style="white-space:pre-wrap;line-height:1.7">{{ item.get("description") or "No written question was provided." }}</div><div class="actions" style="margin-top:14px"><a class="btn secondary" href="{{ url_for('assignment_question_download',assignment_id=item.get('id')) }}">⬇️ Download Question</a>{% if item.get("file_path") %}<a class="btn" href="{{ url_for('assignment_file',assignment_id=item.get('id'),kind='original') }}">⬇️ Download Uploaded Assignment</a>{% endif %}</div></div>
<div class="card"><h3>🔄 Update Assignment Status</h3><form method="post" action="{{ url_for('admin_assignment_status', assignment_id=item.get('id')) }}"><select name="status" required><option value="submitted" {% if item.get('status')=='submitted' %}selected{% endif %}>Submitted</option><option value="under_review" {% if item.get('status')=='under_review' %}selected{% endif %}>Under Review</option><option value="answered" {% if item.get('status')=='answered' %}selected{% endif %}>Answered</option><option value="answer_approved" {% if item.get('status')=='answer_approved' %}selected{% endif %}>Answer Approved</option><option value="answer_sent" {% if item.get('status')=='answer_sent' %}selected{% endif %}>Answer Sent</option><option value="completed" {% if item.get('status')=='completed' %}selected{% endif %}>Completed</option><option value="rejected" {% if item.get('status')=='rejected' %}selected{% endif %}>Rejected</option></select><button class="btn success" type="submit">Update Status</button></form></div>
<div class="card"><form method="post" enctype="multipart/form-data">
<label>Written Answer / User Message</label><textarea name="answer" placeholder="Write the answer or explanation for the user...">{{ item.get("answer") or "" }}</textarea>
<label>Answer PDF</label><input type="file" name="answer_pdf" accept="application/pdf">
<p class="small">Upload the final PDF answer here. Maximum {{ max_upload_mb }} MB.</p>
<button type="submit">Save Answer & PDF</button>
</form></div>
<div class="card"><h3>Send PDF to User</h3>
{% if item.get("answer_file_path") and item.get("answer_approval_status") == "approved" %}
<form method="post" action="{{ url_for('admin_send_assignment_email', assignment_id=item.get('id')) }}">
<label>Recipient Email</label><input type="email" name="recipient_email" value="{{ recipient_email }}" required>
<label>Email Subject</label><input name="subject" value="KOJA AFRICA — Assignment Answer {{ item.get('tracking_code') or '' }}">
<label>Email Message</label><textarea name="message">Hello {{ recipient_name }},\n\nYour KOJA AFRICA assignment answer is attached as a PDF.\n\nTracking code: {{ item.get('tracking_code') or '—' }}\n\nKOJA AFRICA</textarea>
<button class="btn success" type="submit">📧 Send Answer PDF</button>
</form>
{% elif item.get("answer_file_path") %}<p>Answer PDF is uploaded, but it must be <strong>approved</strong> in the Approval Centre before it can be emailed.</p>{% else %}<p>Upload and save an answer PDF first.</p>{% endif %}
</div>
""", item=item, recipient_name=(recipient or {}).get("full_name") or (recipient or {}).get("name") or "User", recipient_email=recipient_email, max_upload_mb=MAX_UPLOAD_MB)

@app.route("/admin/assignments/<assignment_id>/status", methods=["POST"])
@admin_required
def admin_assignment_status(assignment_id):
    item = first_row("assignments", {"id": assignment_id})
    if not item:
        return "Assignment not found.", 404
    allowed_statuses = {"submitted", "under_review", "answered", "answer_approved", "answer_sent", "completed", "rejected"}
    status = clean(request.form.get("status")).lower()
    if status not in allowed_statuses:
        flash("Invalid assignment status.", "danger")
        return redirect(url_for("admin_assignment_answer", assignment_id=assignment_id))
    row, error = db_update("assignments", {"id": assignment_id}, {"status": status, "updated_at": utc_now()})
    if error:
        flash("Status could not be updated. Check the assignments table.", "danger")
    else:
        log_activity("assignment_status_updated", f"Assignment {item.get('tracking_code') or assignment_id} status changed to {status}.")
        flash(f"Assignment status updated to {status.replace('_', ' ').title()}.", "success")
    return redirect(url_for("admin_assignment_answer", assignment_id=assignment_id))

@app.route("/admin/assignments/<assignment_id>/send-email", methods=["POST"])
@admin_required
def admin_send_assignment_email(assignment_id):
    item = first_row("assignments", {"id": assignment_id})
    if not item:
        return "Assignment not found.", 404
    path = item.get("answer_file_path")
    if item.get("answer_approval_status") != "approved":
        flash("This answer must be approved in the Approval Centre before it can be emailed.", "danger")
        return redirect(url_for("admin_assignment_answer", assignment_id=assignment_id))
    if not path:
        flash("No answer PDF has been uploaded for this assignment.", "danger")
        return redirect(url_for("admin_assignment_answer", assignment_id=assignment_id))
    recipient_email, recipient = get_assignment_recipient(item)
    recipient_email = clean(request.form.get("recipient_email")) or recipient_email
    subject = clean(request.form.get("subject")) or f"KOJA AFRICA — Assignment Answer {item.get('tracking_code') or ''}".strip()
    message = request.form.get("message") or f"Hello {(recipient or {}).get('full_name') or 'User'},\n\nYour KOJA AFRICA assignment answer is attached as a PDF.\n\nTracking code: {item.get('tracking_code') or '—'}\n\nKOJA AFRICA"
    try:
        r = requests.get(sb_storage_url(path), headers=sb_headers(), timeout=60)
        if not r.ok:
            flash("The stored answer PDF could not be retrieved.", "danger")
            return redirect(url_for("admin_assignment_answer", assignment_id=assignment_id))
        filename = item.get("answer_file_name") or "KOJA-Assignment-Answer.pdf"
        ok, error = send_email_with_attachment(recipient_email, subject, message, r.content, filename, "application/pdf")
        if ok:
            db_update("assignments", {"id": assignment_id}, {"status": "answer_sent"})
            log_activity("assignment_answer_email_sent", f"Assignment {item.get('tracking_code') or assignment_id} answer PDF emailed to {recipient_email}.")
            flash(f"Answer PDF sent successfully to {recipient_email}.", "success")
        else:
            flash(f"Email could not be sent: {error}", "danger")
    except Exception as exc:
        logger.exception("Assignment PDF email failed")
        flash(f"Email could not be sent: {exc}", "danger")
    return redirect(url_for("admin_assignment_answer", assignment_id=assignment_id))

@app.route("/admin/email", methods=["GET"])
@admin_required
def admin_email_settings():
    gmail_mode = SMTP_HOST.lower() == "smtp.gmail.com"
    return render_page("Admin Email Settings", r"""
<div class="hero"><h2>📧 KOJA Email Management</h2><p>Server-side email delivery for assignment answer PDFs.</p></div>
<div class="card">
<h3>Current configuration</h3>
<table><tr><th>Provider</th><td>{{ "Gmail SMTP" if gmail_mode else "SMTP" }}</td></tr><tr><th>SMTP host</th><td>{{ smtp_host }}</td></tr><tr><th>SMTP port</th><td>{{ smtp_port }}</td></tr><tr><th>From</th><td>{{ smtp_from or "Not configured" }}</td></tr><tr><th>Status</th><td>{{ "Ready" if configured else "Not configured" }}</td></tr></table>
</div>
<div class="card"><h3>How to configure</h3><p>Set these as <strong>Render Environment Variables</strong> — not in the database and not in browser code:</p>
<pre>EMAIL_PROVIDER=smtp
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=yourgmail@gmail.com
SMTP_PASSWORD=your-16-character-google-app-password
SMTP_FROM=yourgmail@gmail.com
SMTP_USE_TLS=true</pre>
<p class="small">For Gmail, enable 2-Step Verification and create a Google App Password. Do not use your normal Gmail password.</p>
<a class="btn" href="{{ url_for('admin_assignments') }}">Back to Assignment Management</a>
</div>
""", gmail_mode=gmail_mode, smtp_host=SMTP_HOST, smtp_port=SMTP_PORT, smtp_from=SMTP_FROM, configured=email_configured())

@app.route("/admin/approvals")
@admin_required
def admin_approvals():
    sections = []
    configs = [
        ("Assignments", "assignments", "approval_status", "title", "assignment"),
        ("Assignment Answers", "assignments", "answer_approval_status", "title", "assignment_answer"),
        ("Doctors", "doctor_profiles", "approval_status", "full_name", "doctor"),
        ("Tutors / Teachers", "teacher_profiles", "approval_status", "full_name", "teacher"),
        ("Drivers", "driver_profiles", "approval_status", "full_name", "driver"),
        ("Professional Providers", "service_providers", "approval_status", "full_name", "provider"),
        ("Documents", "documents", "approval_status", "title", "document"),
        ("Deliveries", "deliveries", "approval_status", "tracking_code", "delivery"),
        ("Appointments", "appointments", "approval_status", "appointment_type", "appointment"),
    ]
    for label, table, status_field, title_field, kind in configs:
        rows = db_select(table, order="created_at.desc", limit=300)
        pending = []
        for row in rows:
            if kind == "assignment_answer":
                if not row.get("answer_file_path") and not row.get("answer"):
                    continue
            status = str(row.get(status_field) or "pending").lower()
            if status in ("pending", "submitted", "requested", "under_review"):
                pending.append(row)
        if pending:
            sections.append({"label": label, "table": table, "kind": kind, "rows": pending, "title_field": title_field})
    return render_page("Admin Approvals", r"""
<div class="hero"><h2>✅ Approval & Review Centre</h2><p>Review submissions before they become active, published, approved or sent to users.</p></div>
<div class="card"><p><strong>Workflow:</strong> User submits → Pending review → Admin approves/rejects → KOJA updates status → optional email notification.</p><p class="small">All approval actions are restricted to administrators and recorded in the activity log.</p></div>
{% for sec in sections %}
<div class="card"><h3>{{ sec.label }} <span class="badge">{{ sec.rows|length }} pending</span></h3>
{% for item in sec.rows %}
<div style="border-top:1px solid var(--border);padding:14px 0">
<strong>{{ item.get(sec.title_field) or item.get('name') or item.get('driver_name') or item.get('doctor_name') or item.get('teacher_name') or 'Submission' }}</strong>
<p class="small">Status: {{ item.get('approval_status') or item.get('answer_approval_status') or 'pending' }}{% if item.get('tracking_code') %} · Tracking: {{ item.get('tracking_code') }}{% endif %}</p>
<form method="post" action="{{ url_for('admin_approval_action', table=sec.table, item_id=item.get('id'), kind=sec.kind) }}" style="display:inline">
<input type="hidden" name="kind" value="{{ sec.kind }}"><input type="hidden" name="action" value="approve"><button class="btn success" type="submit">✓ Approve</button>
</form>
<form method="post" action="{{ url_for('admin_approval_action', table=sec.table, item_id=item.get('id'), kind=sec.kind) }}" style="display:inline;margin-left:8px">
<input type="hidden" name="kind" value="{{ sec.kind }}"><input type="hidden" name="action" value="reject"><input name="note" placeholder="Reason (optional)" style="max-width:260px"><button class="btn danger" type="submit">✕ Reject</button>
</form>
</div>
{% endfor %}</div>
{% else %}<div class="card"><h3>🎉 No pending approvals</h3><p>Everything currently in the approval queue has been reviewed.</p></div>{% endfor %}
""", sections=sections)

@app.route("/admin/approvals/<table>/<item_id>", methods=["POST"])
@admin_required
def admin_approval_action(table, item_id):
    allowed = {"assignments", "doctor_profiles", "teacher_profiles", "driver_profiles", "service_providers", "documents", "deliveries", "appointments"}
    if table not in allowed:
        return "Invalid approval target.", 400
    action = clean(request.form.get("action")).lower()
    if action not in ("approve", "reject"):
        flash("Invalid approval action.", "danger")
        return redirect(url_for("admin_approvals"))
    kind = clean(request.args.get("kind")) or clean(request.form.get("kind"))
    # Answer approval is a separate field on assignments.
    if table == "assignments" and kind == "assignment_answer":
        field = "answer_approval_status"
        event = "assignment_answer_approved" if action == "approve" else "assignment_answer_rejected"
    else:
        field = "approval_status"
        event = f"{table}_approved" if action == "approve" else f"{table}_rejected"
    note = clean(request.form.get("note"))
    updates = {field: "approved" if action == "approve" else "rejected", "approved_by": current_user().get("id"), "approved_at": utc_now(), "approval_note": note or None}
    if table == "assignments":
        # IMPORTANT: assignments.status has an existing database CHECK constraint.
        # Approval is tracked by approval_status / answer_approval_status; do not
        # write the approval label into status because values such as "approved"
        # may violate the existing assignments_status_check constraint.
        if kind == "assignment_answer" and action == "approve":
            updates["status"] = "answered"
        elif action == "reject":
            updates["status"] = "rejected"
        updates["updated_at"] = utc_now()
    row, error = db_update(table, {"id": item_id}, updates)
    if error:
        flash(f"Approval could not be saved: {error}. Make sure the approval migration has been run in Supabase.", "danger")
        return redirect(url_for("admin_approvals"))
    log_activity(event, f"Admin {action} {table} record {item_id}." + (f" Note: {note}" if note else ""))
    # Optional notification to the owner/provider when an email can be resolved.
    recipient = None
    name = "User"
    if table == "assignments":
        # db_update() returns a PostgREST representation as a list. Normalize it
        # before resolving the assignment owner so notification code cannot crash.
        assignment_row = row or first_row(table, {"id": item_id}) or {}
        if isinstance(assignment_row, list):
            assignment_row = assignment_row[0] if assignment_row else {}
        if not isinstance(assignment_row, dict):
            assignment_row = {}
        recipient, profile = get_assignment_recipient(assignment_row)
        name = (profile or {}).get("full_name") or "User"
    else:
        # Supabase/PostgREST PATCH responses are arrays when
        # return=representation is used. Normalize to one record before
        # reading fields so approval notifications never crash with
        # AttributeError: 'list' object has no attribute 'get'.
        current = row or first_row(table, {"id": item_id}) or {}
        if isinstance(current, list):
            current = current[0] if current else {}
        if not isinstance(current, dict):
            current = {}
        uid = current.get("user_id") or current.get("owner_id") or current.get("client_id") or current.get("provider_id")
        if uid:
            profile = first_row("profiles", {"id": uid}) or {}
            recipient = profile.get("email")
            name = profile.get("full_name") or "User"
        recipient = recipient or current.get("email")
    if recipient and email_configured():
        subject = f"KOJA AFRICA — {table.replace('_',' ').title()} {action.title()}"
        body = f"Hello {name},\\n\\nYour KOJA AFRICA submission has been {action}."
        if note: body += f"\\n\\nAdmin note: {note}"
        body += "\\n\\nKOJA AFRICA"
        ok, err = send_plain_email(recipient, subject, body)
        if not ok: logger.warning("Approval notification email failed: %s", err)
    flash(f"{table.replace('_',' ').title()} {'approved' if action == 'approve' else 'rejected'} successfully.", "success")
    return redirect(url_for("admin_approvals"))

@app.route("/admin/drivers")
@admin_required
def admin_drivers():
    rows=db_select("driver_profiles",order="created_at.desc",limit=300)
    return render_page("Admin Drivers",r"""
<div class="card"><h2>Drivers</h2><table><tr><th>Name</th><th>Phone</th><th>Vehicle</th><th>Number</th><th>Provider ID</th></tr>
{% for d in rows %}<tr><td>{{ d.get("full_name") or d.get("driver_name") }}</td><td>{{ d.get("phone") }}</td><td>{{ d.get("vehicle_type") }}</td><td>{{ d.get("vehicle_number") }}</td><td>{{ d.get("provider_id") or d.get("user_id") }}</td></tr>{% endfor %}
</table></div>
""",rows=rows)

@app.route("/admin/live-tracking")
@admin_required
def admin_live_tracking():
    return render_page("Admin Live GPS Tracking", r"""
<div class="hero"><h2>🚚 Live Delivery GPS</h2>
<p>Real-time driver locations received from active KOJA driver phones.</p></div>
<div class="card"><div id="map" style="height:520px;min-height:420px"></div>
<p id="status" class="small">Loading live drivers...</p></div>
<script>
const map=L.map("map").setView([-13.9626,28.3228],6);
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",{maxZoom:19,attribution:"&copy; OpenStreetMap contributors"}).addTo(map);
const markers={};
function esc(v){return String(v??"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/\"/g,"&quot;").replace(/'/g,"&#39;");}
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
</script>
""")

@app.route("/api/admin/live-drivers")
@admin_required
def admin_live_drivers_api():
    if not table_exists("driver_locations"):
        return jsonify({"ok":False,"message":"driver_locations table is not available.","drivers":[]}),503
    locations=latest_driver_locations()
    now=datetime.now(timezone.utc)
    result=[]
    for loc in locations:
        if not loc.get("is_online"):
            continue
        try:
            ts=datetime.fromisoformat(str(loc.get("created_at")).replace("Z","+00:00"))
            if ts.tzinfo is None: ts=ts.replace(tzinfo=timezone.utc)
            age=(now-ts).total_seconds()
            if age > 120: continue
        except Exception:
            age=None
        provider=first_row("driver_profiles", {"provider_id":str(loc.get("driver_id"))})
        name=(provider or {}).get("full_name") or (provider or {}).get("driver_name") or "Driver"
        result.append({"driver_id":str(loc.get("driver_id")),"name":name,"vehicle_type":(provider or {}).get("vehicle_type"),"latitude":loc.get("latitude"),"longitude":loc.get("longitude"),"accuracy":loc.get("accuracy"),"updated_at":loc.get("created_at"),"age_seconds":age})
    return jsonify({"ok":True,"drivers":result})

@app.route("/admin/deliveries")
@admin_required
def admin_deliveries():
    rows=db_select("deliveries",order="created_at.desc",limit=300)
    return render_page("Admin Deliveries",r"""
<div class="card"><h2>Deliveries</h2><table><tr><th>Tracking</th><th>Customer</th><th>Pickup</th><th>Destination</th><th>Driver</th><th>Status</th><th>GPS</th></tr>
{% for d in rows %}<tr><td>{{ d.get("tracking_code") }}</td><td>{{ d.get("customer_id") }}</td><td>{{ d.get("pickup_location") }}</td><td>{{ d.get("destination") }}</td><td>{{ d.get("driver_id") or "Unassigned" }}</td><td>{{ d.get("status") }}</td><td><a class="btn secondary" href="{{ url_for('track_delivery',tracking_code=d.get('tracking_code')) }}" target="_blank">Track GPS</a></td></tr>{% endfor %}
</table></div>
""",rows=rows)


# ============================================================
# SENDER / RECEIVER LIVE GPS SHARING
# ============================================================

def normalize_phone(value):
    return ''.join(ch for ch in str(value or '') if ch.isdigit())

def delivery_participant(delivery):
    user=current_user() or {}
    uid=str(user.get("id") or "")
    if uid and str(delivery.get("customer_id") or delivery.get("user_id") or delivery.get("sender_id") or "") == uid:
        return "sender"
    up=normalize_phone(user.get("phone")); rp=normalize_phone(delivery.get("recipient_phone"))
    if up and rp and (up == rp or up.endswith(rp) or rp.endswith(up)):
        return "receiver"
    return "admin" if user.get("is_admin") else None

@app.route("/delivery/<tracking_code>/sender-live-map")
@login_required
def sender_live_map(tracking_code):
    delivery=first_row("deliveries",{"tracking_code":tracking_code})
    if not delivery:return "Delivery not found.",404
    if delivery_participant(delivery) not in ("sender","admin"):return "Sender access required.",403
    return render_page("Sender & Receiver Live Map", r"""
<div class="hero"><h2>📍 Sender Live Map</h2><p>See your own live location, the receiver's live location and the driver on one map.</p></div>
<div class="card"><div class="actions"><button class="btn success" onclick="startGPS()">Start My GPS</button><button class="btn danger" onclick="stopGPS()">Stop My GPS</button><a class="btn secondary" href="{{ url_for('receiver_live_map',tracking_code=tracking_code) }}">Receiver Screen</a></div><p id="status">Waiting for GPS...</p><div id="map"></div></div>
<script>
const trackingCode={{ tracking_code|tojson }},myRole="sender";const map=L.map("map").setView([-13.9626,28.3228],6);L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",{maxZoom:19,attribution:"&copy; OpenStreetMap contributors"}).addTo(map);const icons={sender:L.divIcon({className:"koja-participant",html:"<div style='font-size:36px'>📤</div>",iconSize:[40,40],iconAnchor:[20,20]}),receiver:L.divIcon({className:"koja-participant",html:"<div style='font-size:36px'>📥</div>",iconSize:[40,40],iconAnchor:[20,20]}),driver:L.divIcon({className:"koja-participant",html:"<div style='font-size:36px'>🚚</div>",iconSize:[40,40],iconAnchor:[20,20]})};let watch=null,markers={};function st(t){document.getElementById("status").textContent=t}function mark(role,p,label){if(!markers[role])markers[role]=L.marker(p,{icon:icons[role]}).addTo(map);markers[role].setLatLng(p).bindPopup(label)}async function send(pos){const c=pos.coords;try{const r=await fetch("/api/delivery/"+encodeURIComponent(trackingCode)+"/participant-location",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({latitude:c.latitude,longitude:c.longitude,accuracy:c.accuracy,speed:c.speed,heading:c.heading,altitude:c.altitude})});const d=await r.json();st(d.ok?"🟢 YOUR GPS LIVE — "+new Date().toLocaleTimeString():(d.message||"GPS update failed"))}catch(e){st("GPS active; network retrying...")}}function startGPS(){if(watch!==null)return;if(!navigator.geolocation){st("GPS is not supported on this device.");return}st("Requesting GPS permission...");watch=navigator.geolocation.watchPosition(p=>{mark("sender",[p.coords.latitude,p.coords.longitude],"📤 YOU — Sender");map.setView([p.coords.latitude,p.coords.longitude],15);send(p)},e=>st(e.code===1?"Allow location permission in browser settings.":"GPS unavailable — retrying..."),{enableHighAccuracy:true,maximumAge:2000,timeout:15000})}function stopGPS(){if(watch!==null){navigator.geolocation.clearWatch(watch);watch=null}fetch("/api/delivery/"+encodeURIComponent(trackingCode)+"/participant-offline",{method:"POST"}).catch(()=>{});st("Your GPS sharing stopped.")}async function refresh(){try{const d=await (await fetch("/api/delivery/"+encodeURIComponent(trackingCode)+"/participant-location",{cache:"no-store"})).json();if(d.ok){if(d.sender)mark("sender",[d.sender.latitude,d.sender.longitude],"📤 Sender");if(d.receiver)mark("receiver",[d.receiver.latitude,d.receiver.longitude],"📥 Receiver");if(d.driver)mark("driver",[d.driver.latitude,d.driver.longitude],"🚚 Driver");st("🟢 LIVE • Sender + Receiver + Driver • "+new Date().toLocaleTimeString())}else st(d.message||"Waiting for live locations...")}catch(e){st("Connection lost — retrying...")}}refresh();setInterval(refresh,3000);
</script>
""",tracking_code=tracking_code)

@app.route("/delivery/<tracking_code>/receiver-live-map")
@login_required
def receiver_live_map(tracking_code):
    delivery=first_row("deliveries",{"tracking_code":tracking_code})
    if not delivery:return "Delivery not found.",404
    if delivery_participant(delivery) not in ("receiver","admin"):return "Receiver access required. The logged-in phone must match the delivery recipient phone.",403
    return render_page("Receiver & Sender Live Map", r"""
<div class="hero"><h2>📍 Receiver Live Map</h2><p>See your own live location, the sender's live location and the driver on one map.</p></div>
<div class="card"><div class="actions"><button class="btn success" onclick="startGPS()">Start My GPS</button><button class="btn danger" onclick="stopGPS()">Stop My GPS</button><a class="btn secondary" href="{{ url_for('sender_live_map',tracking_code=tracking_code) }}">Sender Screen</a></div><p id="status">Waiting for GPS...</p><div id="map"></div></div>
<script>
const trackingCode={{ tracking_code|tojson }},myRole="receiver";const map=L.map("map").setView([-13.9626,28.3228],6);L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",{maxZoom:19,attribution:"&copy; OpenStreetMap contributors"}).addTo(map);const icons={sender:L.divIcon({className:"koja-participant",html:"<div style='font-size:36px'>📤</div>",iconSize:[40,40],iconAnchor:[20,20]}),receiver:L.divIcon({className:"koja-participant",html:"<div style='font-size:36px'>📥</div>",iconSize:[40,40],iconAnchor:[20,20]}),driver:L.divIcon({className:"koja-participant",html:"<div style='font-size:36px'>🚚</div>",iconSize:[40,40],iconAnchor:[20,20]})};let watch=null,markers={};function st(t){document.getElementById("status").textContent=t}function mark(role,p,label){if(!markers[role])markers[role]=L.marker(p,{icon:icons[role]}).addTo(map);markers[role].setLatLng(p).bindPopup(label)}async function send(pos){const c=pos.coords;try{const r=await fetch("/api/delivery/"+encodeURIComponent(trackingCode)+"/participant-location",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({latitude:c.latitude,longitude:c.longitude,accuracy:c.accuracy,speed:c.speed,heading:c.heading,altitude:c.altitude})});const d=await r.json();st(d.ok?"🟢 YOUR GPS LIVE — "+new Date().toLocaleTimeString():(d.message||"GPS update failed"))}catch(e){st("GPS active; network retrying...")}}function startGPS(){if(watch!==null)return;if(!navigator.geolocation){st("GPS is not supported on this device.");return}st("Requesting GPS permission...");watch=navigator.geolocation.watchPosition(p=>{mark("receiver",[p.coords.latitude,p.coords.longitude],"📥 YOU — Receiver");map.setView([p.coords.latitude,p.coords.longitude],15);send(p)},e=>st(e.code===1?"Allow location permission in browser settings.":"GPS unavailable — retrying..."),{enableHighAccuracy:true,maximumAge:2000,timeout:15000})}function stopGPS(){if(watch!==null){navigator.geolocation.clearWatch(watch);watch=null}fetch("/api/delivery/"+encodeURIComponent(trackingCode)+"/participant-offline",{method:"POST"}).catch(()=>{});st("Your GPS sharing stopped.")}async function refresh(){try{const d=await (await fetch("/api/delivery/"+encodeURIComponent(trackingCode)+"/participant-location",{cache:"no-store"})).json();if(d.ok){if(d.sender)mark("sender",[d.sender.latitude,d.sender.longitude],"📤 Sender");if(d.receiver)mark("receiver",[d.receiver.latitude,d.receiver.longitude],"📥 Receiver");if(d.driver)mark("driver",[d.driver.latitude,d.driver.longitude],"🚚 Driver");st("🟢 LIVE • Sender + Receiver + Driver • "+new Date().toLocaleTimeString())}else st(d.message||"Waiting for live locations...")}catch(e){st("Connection lost — retrying...")}}refresh();setInterval(refresh,3000);
</script>
""",tracking_code=tracking_code)

@app.route("/api/delivery/<tracking_code>/participant-location", methods=["GET","POST"])
@login_required
def participant_location_api(tracking_code):
    delivery=first_row("deliveries",{"tracking_code":tracking_code})
    if not delivery:return jsonify({"ok":False,"message":"Delivery not found."}),404
    role=delivery_participant(delivery)
    if role is None:return jsonify({"ok":False,"message":"You are not authorized for this delivery."}),403
    if not table_exists("delivery_participant_locations"):return jsonify({"ok":False,"message":"Run the updated database SQL to enable sender/receiver live GPS."}),503
    if request.method=="POST":
        if role not in ("sender","receiver"):return jsonify({"ok":False,"message":"Only sender or receiver can share GPS."}),403
        body=request.get_json(silent=True) or {};lat=safe_float(body.get("latitude"));lon=safe_float(body.get("longitude"))
        if lat is None or lon is None or not(-90<=lat<=90 and -180<=lon<=180):return jsonify({"ok":False,"message":"Invalid GPS coordinates."}),400
        payload={"id":str(uuid.uuid4()),"delivery_id":str(delivery.get("id")),"user_id":str(current_user().get("id")),"role":role,"latitude":lat,"longitude":lon,"accuracy":safe_float(body.get("accuracy")),"speed":safe_float(body.get("speed")),"heading":safe_float(body.get("heading")),"altitude":safe_float(body.get("altitude")),"is_online":True,"created_at":utc_now()}
        row,error=db_insert("delivery_participant_locations",payload)
        if error:return jsonify({"ok":False,"message":"Could not save participant GPS.","error":str(error)[:400]}),500
        return jsonify({"ok":True,"role":role,"updated_at":payload["created_at"]})
    rows=db_select("delivery_participant_locations",filters={"delivery_id":str(delivery.get("id"))},order="created_at.desc",limit=100);now=datetime.now(timezone.utc);latest={}
    for x in rows:
        rr=x.get("role")
        if rr in latest or not x.get("is_online"):continue
        try:
            ts=datetime.fromisoformat(str(x.get("created_at")).replace("Z","+00:00"));ts=ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
            if (now-ts).total_seconds()>20:continue
        except Exception:pass
        latest[rr]=x
    out={"ok":True,"sender":None,"receiver":None,"driver":None}
    for rr,x in latest.items():out[rr]={"latitude":x.get("latitude"),"longitude":x.get("longitude"),"accuracy":x.get("accuracy"),"speed":x.get("speed"),"heading":x.get("heading"),"updated_at":x.get("created_at")}
    driver_id=delivery.get("driver_id")
    if driver_id:
        locs=db_select("driver_locations",filters={"driver_id":driver_id},order="created_at.desc",limit=1)
        if locs:
            x=locs[0];fresh=True
            try:
                ts=datetime.fromisoformat(str(x.get("created_at")).replace("Z","+00:00"));ts=ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc);fresh=(now-ts).total_seconds()<=20
            except Exception:pass
            if fresh and x.get("is_online"):out["driver"]={"latitude":x.get("latitude"),"longitude":x.get("longitude"),"accuracy":x.get("accuracy"),"speed":x.get("speed"),"heading":x.get("heading"),"updated_at":x.get("created_at")}
    return jsonify(out)

@app.route("/api/delivery/<tracking_code>/participant-offline", methods=["POST"])
@login_required
def participant_offline_api(tracking_code):
    delivery=first_row("deliveries",{"tracking_code":tracking_code})
    if not delivery:return jsonify({"ok":False,"message":"Delivery not found."}),404
    role=delivery_participant(delivery)
    if role not in ("sender","receiver"):return jsonify({"ok":False,"message":"Participant access required."}),403
    if not table_exists("delivery_participant_locations"):return jsonify({"ok":True})
    rows=db_select("delivery_participant_locations",filters={"delivery_id":str(delivery.get("id")),"user_id":str(current_user().get("id"))},order="created_at.desc",limit=1)
    if rows:
        x=rows[0];x["is_online"]=False;x["created_at"]=utc_now();db_insert("delivery_participant_locations",x)
    return jsonify({"ok":True,"message":"Participant GPS sharing stopped."})

# ============================================================
# OWNER LIVE LOCATION + SMART TV LIVE MAP
# ============================================================

@app.route("/owner/live-location")
@admin_required
def owner_live_location():
    return render_page("Owner Live Location", r"""
<div class="hero"><h2>📍 Owner Live Location</h2>
<p>Use the owner's phone to share its real GPS position. Keep this page open while sharing.</p></div>
<div class="card">
  <div class="actions">
    <button class="btn success" onclick="startOwnerGPS()">Start Owner GPS</button>
    <button class="btn danger" onclick="stopOwnerGPS()">Stop GPS</button>
    <a class="btn secondary" href="{{ url_for('admin_live_tv') }}">Open Smart TV Live Map</a>
  </div>
  <p id="owner-status">GPS not started.</p>
  <div id="map"></div>
</div>
<script>
let ownerWatch=null, ownerMarker=null;
const map=L.map("map").setView([-13.9626,28.3228],6);
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",{maxZoom:19,attribution:"&copy; OpenStreetMap contributors"}).addTo(map);
function os(t){document.getElementById("owner-status").textContent=t}
function startOwnerGPS(){
 if(!navigator.geolocation){os("This device does not support GPS.");return}
 if(ownerWatch!==null) return;
 os("Requesting high-accuracy GPS permission...");
 ownerWatch=navigator.geolocation.watchPosition(async pos=>{
   const c=pos.coords;
   if(!ownerMarker) ownerMarker=L.marker([c.latitude,c.longitude]).addTo(map).bindPopup("Owner LIVE location");
   else ownerMarker.setLatLng([c.latitude,c.longitude]);
   map.setView([c.latitude,c.longitude],17,{animate:true});
   try{
     const r=await fetch("{{ url_for('owner_location_update') }}",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({latitude:c.latitude,longitude:c.longitude,accuracy:c.accuracy,speed:c.speed,heading:c.heading,altitude:c.altitude})});
     const d=await r.json(); os(d.ok?"🟢 OWNER LIVE — updated "+new Date().toLocaleTimeString():d.message||"GPS update failed.");
   }catch(e){os("GPS is active but network update failed — retrying...")}
 },e=>{os(e.code===1?"Location permission denied.":e.code===2?"Location unavailable.":"GPS timeout — retrying...")},{enableHighAccuracy:true,maximumAge:2000,timeout:15000});
}
function stopOwnerGPS(){
 if(ownerWatch!==null){navigator.geolocation.clearWatch(ownerWatch);ownerWatch=null;}
 fetch("{{ url_for('owner_location_offline') }}",{method:"POST"}).catch(()=>{});
 os("Owner GPS sharing stopped.");
}
window.addEventListener("pagehide",()=>{if(ownerWatch!==null) navigator.geolocation.clearWatch(ownerWatch);});
</script>
""")

@app.route("/api/owner/location", methods=["POST"])
@admin_required
def owner_location_update():
    body=request.get_json(silent=True) or {}
    lat=safe_float(body.get("latitude")); lon=safe_float(body.get("longitude"))
    if lat is None or lon is None or not (-90<=lat<=90 and -180<=lon<=180):
        return jsonify({"ok":False,"message":"Invalid latitude or longitude."}),400
    if not table_exists("owner_locations"):
        return jsonify({"ok":False,"message":"owner_locations table is not available. Run the updated database SQL."}),503
    payload={"id":str(uuid.uuid4()),"owner_id":str(current_user().get("id")),"latitude":lat,"longitude":lon,
             "accuracy":safe_float(body.get("accuracy")),"speed":safe_float(body.get("speed")),
             "heading":safe_float(body.get("heading")),"altitude":safe_float(body.get("altitude")),
             "is_online":True,"created_at":utc_now()}
    row,error=db_insert("owner_locations",payload)
    if error:
        logger.error("owner_locations insert failed: %s",error)
        return jsonify({"ok":False,"message":"Owner GPS could not be saved.","error":str(error)[:500]}),500
    return jsonify({"ok":True,"latitude":lat,"longitude":lon,"accuracy":payload["accuracy"],"created_at":payload["created_at"]})

@app.route("/api/owner/offline", methods=["POST"])
@admin_required
def owner_location_offline():
    if not table_exists("owner_locations"):
        return jsonify({"ok":True,"message":"Owner GPS sharing stopped locally."})
    latest=db_select("owner_locations",filters={"owner_id":str(current_user().get("id"))},order="created_at.desc",limit=1)
    x=latest[0] if latest else {}
    payload={"id":str(uuid.uuid4()),"owner_id":str(current_user().get("id")),"latitude":x.get("latitude"),"longitude":x.get("longitude"),
             "accuracy":x.get("accuracy"),"speed":None,"heading":None,"altitude":x.get("altitude"),"is_online":False,"created_at":utc_now()}
    db_insert("owner_locations",payload)
    return jsonify({"ok":True,"message":"Owner is now offline."})

@app.route("/admin/live-tv")
@admin_required
def admin_live_tv():
    return render_page("KOJA Smart TV Live Map", r"""
<div style="position:fixed;inset:0;background:#111;z-index:9999">
  <div id="tvmap" style="position:absolute;inset:0"></div>
  <div style="position:absolute;top:18px;left:18px;right:18px;display:flex;justify-content:space-between;align-items:center;pointer-events:none">
    <div style="background:rgba(0,0,0,.78);color:white;padding:12px 18px;border-radius:14px;font-weight:800;font-size:22px">KOJA AFRICA • LIVE</div>
    <div id="tvstatus" style="background:rgba(0,0,0,.78);color:white;padding:10px 15px;border-radius:12px">Connecting...</div>
  </div>
  <div style="position:absolute;bottom:18px;left:18px;background:rgba(0,0,0,.78);color:white;padding:12px 16px;border-radius:14px;pointer-events:none">
    <b>🟢 LIVE</b> • Drivers + Owner GPS • Auto refresh
  </div>
</div>
<script>
const tvmap=L.map("tvmap",{zoomControl:false}).setView([-13.9626,28.3228],6);
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",{maxZoom:19,attribution:"&copy; OpenStreetMap contributors"}).addTo(tvmap);
const tvMarkers={}; let ownerMarker=null;
const truckIcon=L.divIcon({className:"koja-tv-truck",html:"<div style='font-size:36px'>🚚</div>",iconSize:[40,40],iconAnchor:[20,20]});
const ownerIcon=L.divIcon({className:"koja-tv-owner",html:"<div style='font-size:36px'>👤</div>",iconSize:[40,40],iconAnchor:[20,20]});
function esc(v){return String(v??"").replace(/[&<>\"']/g,m=>({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[m]));}
async function refreshTV(){
 try{
   const [dr,ow]=await Promise.all([fetch("{{ url_for('admin_live_drivers_api') }}",{cache:"no-store"}),fetch("{{ url_for('owner_live_api') }}",{cache:"no-store"})]);
   const d=await dr.json(),o=await ow.json(); let count=0;
   if(d.ok){const seen={}; (d.drivers||[]).forEach(x=>{seen[x.driver_id]=true;count++;const p=[Number(x.latitude),Number(x.longitude)];if(!tvMarkers[x.driver_id])tvMarkers[x.driver_id]=L.marker(p,{icon:truckIcon}).addTo(tvmap);else tvMarkers[x.driver_id].setLatLng(p);tvMarkers[x.driver_id].bindPopup("<b>🚚 "+esc(x.name)+"</b><br>LIVE<br>Accuracy: "+esc(x.accuracy||"—")+" m");});Object.keys(tvMarkers).forEach(id=>{if(!seen[id]){tvmap.removeLayer(tvMarkers[id]);delete tvMarkers[id];}});}
   if(o.ok&&o.location){const p=[Number(o.location.latitude),Number(o.location.longitude)];if(!ownerMarker)ownerMarker=L.marker(p,{icon:ownerIcon}).addTo(tvmap);else ownerMarker.setLatLng(p);ownerMarker.bindPopup("<b>👤 OWNER</b><br>LIVE location<br>Accuracy: "+esc(o.location.accuracy||"—")+" m");count++;}
   document.getElementById("tvstatus").textContent="🟢 "+count+" live location(s) • "+new Date().toLocaleTimeString();
 }catch(e){document.getElementById("tvstatus").textContent="🔴 Connection lost — retrying";}
}
async function ownerLive(){return null}
refreshTV();setInterval(refreshTV,3000);
</script>
""")

@app.route("/api/admin/owner-live")
@admin_required
def owner_live_api():
    if not table_exists("owner_locations"):
        return jsonify({"ok":True,"location":None})
    rows=db_select("owner_locations",order="created_at.desc",limit=1)
    if not rows or not rows[0].get("is_online"):
        return jsonify({"ok":True,"location":None})
    loc=rows[0]
    try:
        ts=datetime.fromisoformat(str(loc.get("created_at")).replace("Z","+00:00"));
        if ts.tzinfo is None: ts=ts.replace(tzinfo=timezone.utc)
        age=max(0,(datetime.now(timezone.utc)-ts).total_seconds())
        if age>30:return jsonify({"ok":True,"location":None})
    except Exception: pass
    return jsonify({"ok":True,"location":{"latitude":loc.get("latitude"),"longitude":loc.get("longitude"),"accuracy":loc.get("accuracy"),"speed":loc.get("speed"),"heading":loc.get("heading"),"updated_at":loc.get("created_at")}})

@app.route("/admin/appointments")
@admin_required
def admin_appointments():
    rows=db_select("appointments",order="created_at.desc",limit=300)
    return render_page("Admin Appointments",r"""
<div class="card"><h2>Appointments</h2><table><tr><th>Date</th><th>Client</th><th>Provider</th><th>Type</th><th>Status</th></tr>
{% for a in rows %}<tr><td>{{ a.get("appointment_date") }}</td><td>{{ a.get("client_id") }}</td><td>{{ a.get("provider_id") }}</td><td>{{ a.get("appointment_type") }}</td><td>{{ a.get("status") }}</td></tr>{% endfor %}
</table></div>
""",rows=rows)

# ============================================================
# KOJA CONNECT — GENERAL SOCIAL COMMUNICATION
# Separate from Professional Services communication.
# ============================================================

KOJA_CONNECT_SQL = r"""
create table if not exists public.koja_contacts (
 id uuid primary key default gen_random_uuid(), requester_id uuid not null, addressee_id uuid not null,
 status text not null default 'pending', created_at timestamptz default now(), updated_at timestamptz default now(),
 unique(requester_id, addressee_id)
);
create index if not exists koja_contacts_requester_idx on public.koja_contacts(requester_id, status);
create index if not exists koja_contacts_addressee_idx on public.koja_contacts(addressee_id, status);
create table if not exists public.koja_conversations (
 id uuid primary key default gen_random_uuid(), conversation_type text not null default 'direct', created_by uuid,
 name text, avatar_url text, created_at timestamptz default now(), updated_at timestamptz default now()
);
create table if not exists public.koja_conversation_members (
 conversation_id uuid not null references public.koja_conversations(id) on delete cascade,
 user_id uuid not null, role text not null default 'member', joined_at timestamptz default now(), last_read_at timestamptz,
 muted boolean default false, primary key(conversation_id,user_id)
);
create index if not exists koja_members_user_idx on public.koja_conversation_members(user_id, conversation_id);
create table if not exists public.koja_messages (
 id uuid primary key default gen_random_uuid(), conversation_id uuid not null references public.koja_conversations(id) on delete cascade,
 sender_id uuid not null, message_type text not null default 'text', body text default '', file_url text,
 created_at timestamptz default now(), edited_at timestamptz, deleted_at timestamptz
);
create index if not exists koja_messages_conversation_idx on public.koja_messages(conversation_id, created_at);
create table if not exists public.koja_calls (
 id uuid primary key default gen_random_uuid(), conversation_id uuid not null references public.koja_conversations(id) on delete cascade,
 caller_id uuid not null, callee_id uuid not null, mode text not null default 'video', status text not null default 'ringing',
 offer text, answer text, caller_ice jsonb default '[]'::jsonb, callee_ice jsonb default '[]'::jsonb,
 created_at timestamptz default now(), answered_at timestamptz, ended_at timestamptz
);
create index if not exists koja_calls_callee_idx on public.koja_calls(callee_id,status,created_at desc);
create index if not exists koja_calls_caller_idx on public.koja_calls(caller_id,status,created_at desc);
create table if not exists public.koja_presence (
 user_id uuid primary key, is_online boolean default false, last_seen_at timestamptz default now(), updated_at timestamptz default now()
);
create table if not exists public.koja_statuses (
 id uuid primary key default gen_random_uuid(), user_id uuid not null, text_content text default '', media_url text,
 media_type text default 'text', visibility text not null default 'contacts',
 expires_at timestamptz not null default (now()+interval '24 hours'), created_at timestamptz default now()
);
create index if not exists koja_statuses_user_idx on public.koja_statuses(user_id,created_at desc);
create table if not exists public.koja_notifications (
 id uuid primary key default gen_random_uuid(), user_id uuid not null, notification_type text, title text, body text, related_id uuid,
 is_read boolean default false, created_at timestamptz default now()
);
create index if not exists koja_notifications_user_idx on public.koja_notifications(user_id,is_read,created_at desc);
create table if not exists public.koja_blocks (
 blocker_id uuid not null, blocked_id uuid not null, created_at timestamptz default now(), primary key(blocker_id,blocked_id)
);
create table if not exists public.koja_push_tokens (
 id uuid primary key default gen_random_uuid(), user_id uuid not null, token text not null unique, platform text not null default 'android',
 device_name text, enabled boolean not null default true, created_at timestamptz default now(), updated_at timestamptz default now(), last_seen_at timestamptz default now()
);
create index if not exists koja_push_tokens_user_idx on public.koja_push_tokens(user_id,enabled,updated_at desc);
create index if not exists koja_push_tokens_token_idx on public.koja_push_tokens(token);
"""

def _connect_user(uid): return find_user_by_id(uid) or {}
def _conversation_member(cid, uid): return bool(first_row('koja_conversation_members', {'conversation_id':cid,'user_id':uid}))
def _profile_name(uid):
    u=_connect_user(uid); return first_nonempty(u.get('full_name'),u.get('name'),u.get('email'),'KOJA User')

def _direct_conversation(a,b):
    """Find or create a direct conversation. Calling does not require a contact relationship."""
    a,b=str(a),str(b)
    if not a or not b or a==b:
        return None
    rows=db_select('koja_conversation_members',filters={'user_id':a},limit=200)
    for m in rows:
        cid=m.get('conversation_id')
        if cid and _conversation_member(cid,b):
            c=first_row('koja_conversations',{'id':cid})
            if c and str(c.get('conversation_type') or 'direct')=='direct':
                return c
    c,err=db_insert('koja_conversations',{'id':str(uuid.uuid4()),'conversation_type':'direct','created_by':a,'created_at':utc_now(),'updated_at':utc_now()})
    if err or not c:
        logger.error('KOJA Connect conversation create failed: %s', err)
        return None
    cid=c['id']
    _,e1=db_insert('koja_conversation_members',{'conversation_id':cid,'user_id':a,'role':'member','joined_at':utc_now()})
    _,e2=db_insert('koja_conversation_members',{'conversation_id':cid,'user_id':b,'role':'member','joined_at':utc_now()})
    if e1 or e2:
        logger.error('KOJA Connect member creation failed: first=%s second=%s', e1, e2)
        db_delete('koja_conversations',{'id':cid})
        return None
    return c

def _firebase_project_id():
    return clean(os.getenv('FIREBASE_PROJECT_ID'))

def _send_fcm_to_user(user_id, data):
    """Send incoming-call push through the keyless Firebase Cloud Function relay.

    Render never holds a Google service-account private key. The relay runs inside
    Firebase/Google Cloud and uses its attached service identity/ADC to call FCM.
    Render authenticates to the relay with a separate HMAC-style shared secret.
    """
    relay=clean(os.getenv('FCM_RELAY_URL'))
    secret=clean(os.getenv('FCM_RELAY_SECRET'))
    if not relay or not secret:
        logger.info('FCM relay not configured; stored in-app notification only for user %s', user_id)
        return {'sent':0,'configured':False,'mode':'keyless-relay'}
    try:
        tokens=db_select('koja_push_tokens',filters={'user_id':str(user_id),'enabled':True},limit=50)
        tokens=[clean(x.get('token')) for x in tokens if clean(x.get('token'))]
        if not tokens:
            return {'sent':0,'configured':True,'mode':'keyless-relay','tokens':0}
        payload={'tokens':tokens,'data':{str(k):clean(v) for k,v in data.items()}}
        r=requests.post(relay,headers={'X-KOJA-Relay-Secret':secret,'Content-Type':'application/json'},json=payload,timeout=20)
        if not r.ok:
            logger.warning('FCM relay failed: %s %s',r.status_code,r.text[:500])
            return {'sent':0,'configured':True,'mode':'keyless-relay','error':'relay request failed','status':r.status_code}
        result=r.json() if r.content else {}
        for token in result.get('invalid_tokens',[]) or []:
            db_update('koja_push_tokens',{'token':token},{'enabled':False,'updated_at':utc_now()})
        return {'sent':int(result.get('sent',0) or 0),'configured':True,'mode':'keyless-relay','tokens':len(tokens),'invalid':len(result.get('invalid_tokens',[]) or [])}
    except Exception as exc:
        logger.exception('FCM keyless relay error: %s',exc)
        return {'sent':0,'configured':True,'mode':'keyless-relay','error':'relay unavailable'}

@app.route('/api/connect/push-token',methods=['POST'])
@login_required
def connect_push_token():
    uid=current_user()['id']; d=request.get_json(silent=True) or {}
    token=clean(d.get('token')); platform=clean(d.get('platform','android')).lower() or 'android'
    if len(token)<20 or len(token)>4096: return jsonify(error='Invalid push token'),400
    if platform not in ('android','web'): platform='android'
    # Token migration-safe upsert: remove old ownership, then create current record.
    db_delete('koja_push_tokens',{'token':token})
    row,err=db_insert('koja_push_tokens',{'id':str(uuid.uuid4()),'user_id':uid,'token':token,'platform':platform,'device_name':clean(d.get('device_name'))[:120],'enabled':True,'created_at':utc_now(),'updated_at':utc_now(),'last_seen_at':utc_now()})
    if err: return jsonify(error=err),500
    return jsonify(ok=True,token_id=row.get('id') if row else None)

@app.route('/api/connect/push-token',methods=['DELETE'])
@login_required
def connect_push_token_delete():
    uid=current_user()['id']; token=clean((request.get_json(silent=True) or {}).get('token'))
    if token: db_update('koja_push_tokens',{'token':token},{'enabled':False,'updated_at':utc_now()})
    return jsonify(ok=True)

@app.route('/api/connect/call/create',methods=['POST'])
@login_required
def connect_call_create():
    uid=current_user()['id']; d=request.get_json(silent=True) or {}; callee=clean(d.get('callee_id')); mode=clean(d.get('mode','video')).lower()
    if not callee or callee==str(uid) or not find_user_by_id(callee) or mode not in ('voice','video'): return jsonify(error='Invalid call'),400
    # Calls are deliberately independent of contact/connection status.
    c=_direct_conversation(uid,callee)
    if not c: return jsonify(error='Unable to create the KOJA conversation. Run the KOJA Connect SQL in the active Supabase project and verify the service key.'),500
    row,err=db_insert('koja_calls',{'id':str(uuid.uuid4()),'conversation_id':c['id'],'caller_id':uid,'callee_id':callee,'mode':mode,'status':'ringing','created_at':utc_now()})
    if err or not row: return jsonify(error=err or 'Unable to create call'),500
    db_insert('koja_notifications',{'user_id':callee,'notification_type':'call','title':f'Incoming {mode} call','body':f'{_profile_name(uid)} is calling you.','related_id':row['id']})
    push=_send_fcm_to_user(callee,{'type':'incoming_call','call_id':row['id'],'caller_id':str(uid),'caller_name':_profile_name(uid),'mode':mode,'title':f'Incoming {mode} call','body':f'{_profile_name(uid)} is calling you.'})
    return jsonify(call=row,push=push)

@app.route('/api/connect/call/offer/<call_id>',methods=['POST'])
@login_required
def connect_call_offer(call_id):
    uid=current_user()['id']; c=first_row('koja_calls',{'id':call_id})
    if not c or str(c.get('caller_id'))!=str(uid):return jsonify(error='Forbidden'),403
    d=request.get_json(silent=True) or {};db_update('koja_calls',{'id':call_id},{'offer':clean(d.get('offer'))});return jsonify(ok=True)

@app.route('/api/connect/call/check/<call_id>')
@login_required
def connect_call_check(call_id):
    uid=current_user()['id'];c=first_row('koja_calls',{'id':call_id})
    if not c or uid not in (str(c.get('caller_id')),str(c.get('callee_id'))):return jsonify(error='Forbidden'),403
    return jsonify(call=c)

@app.route('/api/connect/call/reject/<call_id>',methods=['POST'])
@login_required
def connect_call_reject(call_id):
    uid=current_user()['id']; c=first_row('koja_calls',{'id':call_id})
    if not c or str(c.get('callee_id'))!=str(uid): return jsonify(error='Forbidden'),403
    db_update('koja_calls',{'id':call_id},{'status':'rejected','ended_at':utc_now()})
    return jsonify(ok=True)

@app.route('/api/connect/call/ice/<call_id>',methods=['POST','GET'])
@login_required
def connect_call_ice(call_id):
    uid=current_user()['id']; c=first_row('koja_calls',{'id':call_id})
    if not c or str(uid) not in (str(c.get('caller_id')),str(c.get('callee_id'))): return jsonify(error='Forbidden'),403
    if request.method=='GET':
        side='callee_ice' if str(uid)==str(c.get('caller_id')) else 'caller_ice'
        return jsonify(candidates=c.get(side) or [])
    d=request.get_json(silent=True) or {}; candidate=d.get('candidate')
    if not candidate: return jsonify(error='Missing candidate'),400
    side='caller_ice' if str(uid)==str(c.get('caller_id')) else 'callee_ice'
    current=c.get(side) or []
    if not isinstance(current,list): current=[]
    # Accept one RTCIceCandidate JSON object or an array; cap to avoid abuse.
    incoming=candidate if isinstance(candidate,list) else [candidate]
    for item in incoming:
        if isinstance(item,dict) and item not in current: current.append(item)
    current=current[-100:]
    _,err=db_update('koja_calls',{'id':call_id},{side:current})
    if err: return jsonify(error=err),500
    return jsonify(ok=True)

@app.route('/api/connect/call/end/<call_id>',methods=['POST'])
@login_required
def connect_call_end(call_id):
    uid=current_user()['id'];c=first_row('koja_calls',{'id':call_id})
    if not c or uid not in (str(c.get('caller_id')),str(c.get('callee_id'))):return jsonify(error='Forbidden'),403
    db_update('koja_calls',{'id':call_id},{'status':'ended','ended_at':utc_now()});return jsonify(ok=True)

@app.route('/connect')
@login_required
def connect():
    uid=current_user()['id']; members=db_select('koja_conversation_members',filters={'user_id':uid},limit=100); conversations=[]
    for m in members:
        c=first_row('koja_conversations',{'id':m.get('conversation_id')})
        if not c: continue
        others=db_select('koja_conversation_members',filters={'conversation_id':c['id']},limit=10); other=next((x for x in others if str(x.get('user_id'))!=str(uid)),None)
        c['_other_name']=_profile_name(other['user_id']) if other else (c.get('name') or 'Group'); last=db_select('koja_messages',filters={'conversation_id':c['id']},order='created_at.desc',limit=1); c['_last']=(last[0].get('body') or last[0].get('message_type','')) if last else 'No messages yet'; conversations.append(c)
    return render_page('KOJA Connect',r'''<div class="hero"><h2>💬 KOJA Connect</h2><p>Chat, voice messages, voice calls, video calls, photos, files, groups and status updates with other KOJA users.</p></div><div class="grid"><div class="card"><h3>👥 Find People</h3><p>Search KOJA users and start a conversation.</p><a class="btn" href="{{ url_for('connect_people') }}">Find People</a></div><div class="card"><h3>🟢 Status</h3><p>Share a 24-hour status.</p><a class="btn" href="{{ url_for('connect_status') }}">My Status</a></div><div class="card"><h3>📞 Calls</h3><p>Voice and video calls separate from Professional Services.</p><a class="btn" href="{{ url_for('connect_calls') }}">Call History</a></div></div><div class="card"><h3>Recent Chats</h3>{% for c in conversations %}<a class="card" style="display:block;text-decoration:none;color:inherit" href="{{ url_for('connect_chat',conversation_id=c.id) }}"><strong>{{ c._other_name }}</strong><div class="small">{{ c._last }}</div></a>{% else %}<p>No chats yet. Find a KOJA user to start.</p>{% endfor %}</div>''',conversations=conversations)

@app.route('/connect/people',methods=['GET','POST'])
@login_required
def connect_people():
    uid=current_user()['id']
    if request.method=='POST':
        target=clean(request.form.get('user_id')); existing=first_row('koja_contacts',{'requester_id':uid,'addressee_id':target}) or first_row('koja_contacts',{'requester_id':target,'addressee_id':uid})
        if target and target!=uid and find_user_by_id(target) and not existing:
            db_insert('koja_contacts',{'id':str(uuid.uuid4()),'requester_id':uid,'addressee_id':target,'status':'pending','created_at':utc_now(),'updated_at':utc_now()}); db_insert('koja_notifications',{'user_id':target,'notification_type':'friend_request','title':'New KOJA connection request','body':f'{_profile_name(uid)} wants to connect on KOJA.','related_id':uid}); flash('Connection request sent.','success')
        else: flash('User not found or request already exists.','warning')
        return redirect(url_for('connect_people'))
    q=clean(request.args.get('q')); people=[]
    if q:
        for col in ('email','full_name','name'):
            for x in db_select('profiles',filters={col:f'ilike.*{q}*'},limit=30):
                if str(x.get('id'))!=str(uid) and not any(str(p.get('id'))==str(x.get('id')) for p in people): people.append(x)
    incoming=db_select('koja_contacts',filters={'addressee_id':uid,'status':'pending'},limit=50)
    return render_page('KOJA People',r'''<div class="card"><h2>Find KOJA People</h2><form><input name="q" value="{{ q }}" placeholder="Search name or email"><button>Search</button></form></div><div class="grid">{% for p in people %}<div class="card"><h3>{{ p.get('full_name') or p.get('name') or p.get('email') }}</h3><p>{{ p.get('email') or '' }}</p><form method="post"><input type="hidden" name="user_id" value="{{ p.id }}"><button>➕ Connect</button></form><a class="btn secondary" href="{{ url_for('connect_new',user_id=p.id) }}">Message</a></div>{% endfor %}</div><div class="card"><h3>Incoming Requests</h3>{% for r in incoming %}<div class="card"><strong>{{ _profile_name(r.requester_id) }}</strong><form method="post" action="{{ url_for('connect_accept',contact_id=r.id) }}"><button>Accept</button></form></div>{% else %}<p>No pending requests.</p>{% endfor %}</div>''',people=people,q=q,incoming=incoming,_profile_name=_profile_name)

@app.route('/connect/accept/<contact_id>',methods=['POST'])
@login_required
def connect_accept(contact_id):
    uid=current_user()['id']; r=first_row('koja_contacts',{'id':contact_id})
    if not r or str(r.get('addressee_id'))!=str(uid): abort(404)
    db_update('koja_contacts',{'id':contact_id},{'status':'accepted','updated_at':utc_now()}); _direct_conversation(uid,r['requester_id']); flash('Connection accepted.','success'); return redirect(url_for('connect_people'))

@app.route('/connect/new/<user_id>')
@login_required
def connect_new(user_id):
    uid=current_user()['id']
    if user_id==uid or not find_user_by_id(user_id): abort(404)
    c=_direct_conversation(uid,user_id)
    if not c: flash('Could not start chat. Run the KOJA Connect SQL first.','danger'); return redirect(url_for('connect'))
    return redirect(url_for('connect_chat',conversation_id=c['id']))

@app.route('/connect/chat/<conversation_id>')
@login_required
def connect_chat(conversation_id):
    uid=current_user()['id'];
    if not _conversation_member(conversation_id,uid): abort(403)
    members=db_select('koja_conversation_members',filters={'conversation_id':conversation_id},limit=100); other=next((m for m in members if str(m.get('user_id'))!=str(uid)),None); other_id=other.get('user_id') if other else None; c=first_row('koja_conversations',{'id':conversation_id}) or {}
    return render_page('KOJA Chat',r'''<div class="card"><a href="{{ url_for('connect') }}">← Connect</a><h2>💬 {{ name }}</h2></div><div class="card" id="messages" style="min-height:300px;max-height:55vh;overflow:auto"></div><div class="card"><form id="sendForm"><input id="text" autocomplete="off" placeholder="Write a message…"><button>Send</button></form><div class="grid"><button type="button" id="voiceNote">🎙️ Voice message</button><a class="btn" href="{{ url_for('connect_call',user_id=other_id,mode='voice') }}">📞 Voice Call</a><a class="btn" href="{{ url_for('connect_call',user_id=other_id,mode='video') }}">🎥 Video Call</a></div></div><script>const cid={{ conversation_id|tojson }};const box=document.getElementById('messages');const text=document.getElementById('text');async function load(){let r=await fetch('/api/connect/messages/'+cid);if(!r.ok)return;let d=await r.json();box.innerHTML=d.messages.map(m=>'<div class="card"><strong>'+m.sender_name+'</strong><div>'+((m.message_type==='text')?(m.body||''):'<a target="_blank" href="'+m.file_url+'">'+m.message_type+'</a>')+'</div><div class="small">'+(m.created_at||'')+'</div></div>').join('');box.scrollTop=box.scrollHeight;}document.getElementById('sendForm').onsubmit=async e=>{e.preventDefault();let v=text.value.trim();if(!v)return;let r=await fetch('/api/connect/messages/'+cid,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:v})});if(r.ok){text.value='';load();}};load();setInterval(load,2500);let rec,parts=[];document.getElementById('voiceNote').onclick=async()=>{try{let st=await navigator.mediaDevices.getUserMedia({audio:true});rec=new MediaRecorder(st);parts=[];rec.ondataavailable=e=>parts.push(e.data);rec.onstop=async()=>{let b=new Blob(parts,{type:'audio/webm'});let fd=new FormData();fd.append('file',b,'voice.webm');await fetch('/api/connect/messages/'+cid+'/upload',{method:'POST',body:fd});st.getTracks().forEach(t=>t.stop());load();};rec.start();setTimeout(()=>rec&&rec.state==='recording'&&rec.stop(),60000);}catch(e){alert('Microphone permission is required.');}};</script>''',conversation_id=conversation_id,name=_profile_name(other_id) if other_id else c.get('name','KOJA Chat'))

@app.route('/api/connect/messages/<conversation_id>',methods=['GET','POST'])
@login_required
def connect_messages(conversation_id):
    uid=current_user()['id']
    if not _conversation_member(conversation_id,uid): return jsonify(error='Forbidden'),403
    if request.method=='POST':
        d=request.get_json(silent=True) or {}; body=clean(d.get('message'))
        if not body:return jsonify(error='Empty message'),400
        row,err=db_insert('koja_messages',{'id':str(uuid.uuid4()),'conversation_id':conversation_id,'sender_id':uid,'message_type':'text','body':body,'created_at':utc_now()})
        if err:return jsonify(error=err),500
        return jsonify(message=row)
    rows=db_select('koja_messages',filters={'conversation_id':conversation_id},order='created_at.asc',limit=300)
    for m in rows:m['sender_name']=_profile_name(m.get('sender_id'))
    return jsonify(messages=rows)

@app.route('/api/connect/messages/<conversation_id>/upload',methods=['POST'])
@login_required
def connect_upload(conversation_id):
    uid=current_user()['id']
    if not _conversation_member(conversation_id,uid):return jsonify(error='Forbidden'),403
    f=request.files.get('file')
    if not f:return jsonify(error='No file'),400
    if not f.filename.lower().endswith('.webm'):return jsonify(error='Only webm voice messages are supported here.'),400
    data=f.read()
    if len(data)>5*1024*1024:return jsonify(error='Voice message too large'),413
    path=f'connect/audio/{uuid.uuid4().hex}.webm'; r=requests.post(sb_storage_url(path),headers=sb_headers({'Content-Type':'audio/webm','x-upsert':'true'}),data=data,timeout=60)
    if not r.ok:return jsonify(error=r.text[:500]),500
    row,err=db_insert('koja_messages',{'id':str(uuid.uuid4()),'conversation_id':conversation_id,'sender_id':uid,'message_type':'audio','file_url':sb_storage_url(path),'body':'Voice message','created_at':utc_now()})
    return jsonify(message=row) if not err else (jsonify(error=err),500)

@app.route('/connect/status',methods=['GET','POST'])
@login_required
def connect_status():
    uid=current_user()['id']
    if request.method=='POST':
        body=clean(request.form.get('text'))
        if body:db_insert('koja_statuses',{'id':str(uuid.uuid4()),'user_id':uid,'text_content':body,'media_type':'text','visibility':'contacts','expires_at':(datetime.now(timezone.utc)+timedelta(hours=24)).isoformat(),'created_at':utc_now()});flash('Status posted for 24 hours.','success')
        return redirect(url_for('connect_status'))
    rows=db_select('koja_statuses',filters={'user_id':uid},order='created_at.desc',limit=30)
    return render_page('KOJA Status',r'''<div class="card"><h2>🟢 My Status</h2><form method="post"><textarea name="text" maxlength="1000" placeholder="Share an update…"></textarea><button>Post Status</button></form></div>{% for s in rows %}<div class="card"><strong>{{ s.text_content }}</strong><div class="small">Expires: {{ s.expires_at }}</div></div>{% endfor %}''',rows=rows)

@app.route('/connect/answer/<call_id>')
@login_required
def connect_answer(call_id):
    uid=current_user()['id']; c=first_row('koja_calls',{'id':call_id})
    if not c or str(c.get('callee_id'))!=str(uid) or c.get('status')!='ringing': abort(404)
    return render_page('Answer KOJA Call',r'''<div class="card"><h2>📞 Incoming {{ c.mode|title }} Call</h2><p>From <strong>{{ name }}</strong></p><div id="state">Connecting…</div><div style="display:grid;grid-template-columns:1fr 1fr;gap:10px"><video id="local" autoplay muted playsinline style="width:100%;background:#111;border-radius:10px"></video><video id="remote" autoplay playsinline style="width:100%;background:#111;border-radius:10px"></video></div><button id="hang" class="btn danger">End Call</button></div><script>const cid={{ call_id|tojson }},mode={{ c.mode|tojson }};let pc=null,timer=null;async function api(u,o){let r=await fetch(u,o);if(!r.ok)throw 0;return r.json()}async function start(){try{let x=await api('/api/connect/call/check/'+cid);if(!x.call.offer)throw 0;pc=new RTCPeerConnection({iceServers:[{urls:'stun:stun.l.google.com:19302'}]});let st=await navigator.mediaDevices.getUserMedia({audio:true,video:mode==='video'});local.srcObject=st;st.getTracks().forEach(t=>pc.addTrack(t,st));pc.ontrack=e=>remote.srcObject=e.streams[0];pc.onicecandidate=e=>{if(e.candidate)fetch('/api/connect/call/ice/'+cid,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({candidate:e.candidate})})};await pc.setRemoteDescription({type:'offer',sdp:x.call.offer});let ans=await pc.createAnswer();await pc.setLocalDescription(ans);await api('/api/connect/call/answer/'+cid,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({answer:ans.sdp})});state.textContent='Connected';timer=setInterval(async()=>{try{let z=await api('/api/connect/call/check/'+cid);if(z.call.status==='ended'){clearInterval(timer);pc.close();state.textContent='Call ended'}}catch(e){}},1500)}catch(e){state.textContent='Could not answer this call.'}}hang.onclick=()=>{fetch('/api/connect/call/end/'+cid,{method:'POST'});clearInterval(timer);if(pc)pc.close();state.textContent='Call ended'};start();</script>''',c=c,call_id=call_id,name=_profile_name(c.get('caller_id')))

@app.route('/api/connect/call/answer/<call_id>',methods=['POST'])
@login_required
def connect_call_answer(call_id):
    uid=current_user()['id'];c=first_row('koja_calls',{'id':call_id})
    if not c or str(c.get('callee_id'))!=str(uid):return jsonify(error='Forbidden'),403
    d=request.get_json(silent=True) or {};db_update('koja_calls',{'id':call_id},{'answer':clean(d.get('answer')),'status':'answered','answered_at':utc_now()});return jsonify(ok=True)

@app.route('/connect/calls')
@login_required
def connect_calls():
    uid=current_user()['id']; rows=db_select('koja_calls',filters={'caller_id':uid},order='created_at.desc',limit=50)+db_select('koja_calls',filters={'callee_id':uid},order='created_at.desc',limit=50); rows=sorted(rows,key=lambda x:x.get('created_at',''),reverse=True)[:50]
    return render_page('KOJA Calls',r'''<div class="card"><h2>📞 KOJA Call History</h2>{% for c in rows %}<div class="card"><strong>{{ c.mode|title }}</strong> — {{ c.status }}<div class="small">{{ c.created_at }}</div>{% if c.callee_id|string == user.id|string and c.status=='ringing' %}<a class="btn" href="{{ url_for('connect_answer',call_id=c.id) }}">Answer</a>{% endif %}</div>{% else %}<p>No calls yet.</p>{% endfor %}</div>''',rows=rows)

@app.route('/connect/call/<user_id>')
@login_required
def connect_call(user_id):
    uid=current_user()['id']; mode=clean(request.args.get('mode','video'))
    if user_id==uid or not find_user_by_id(user_id) or mode not in ('voice','video'):abort(404)
    c=_direct_conversation(uid,user_id)
    if not c:return 'Run KOJA Connect SQL first.',500
    return render_page('KOJA Call',r'''<div class="card"><h2>📞 KOJA {{ mode|title }} Call</h2><p>Calling <strong>{{ name }}</strong></p><div id="state">Connecting…</div><div style="display:grid;grid-template-columns:1fr 1fr;gap:10px"><video id="local" autoplay muted playsinline style="width:100%;background:#111;border-radius:10px"></video><video id="remote" autoplay playsinline style="width:100%;background:#111;border-radius:10px"></video></div><button id="hang" class="btn danger">End Call</button></div><script>const target={{ user_id|tojson }},mode={{ mode|tojson }};let callId=null,pc=null,timer=null,started=Date.now();const state=document.getElementById('state');const unavailable='This contact is not available because the internet or network connection could not be reached.';function speak(){if('speechSynthesis'in window){speechSynthesis.cancel();speechSynthesis.speak(new SpeechSynthesisUtterance(unavailable));}}function fail(msg){state.textContent=msg||unavailable;speak();clearInterval(timer);if(pc)pc.close();}async function api(u,o){let r=await fetch(u,o);if(!r.ok)throw 0;return r.json()}async function start(){try{if(!navigator.onLine)throw 0;let c=await api('/api/connect/call/create',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({callee_id:target,mode})});callId=c.call.id;pc=new RTCPeerConnection({iceServers:[{urls:'stun:stun.l.google.com:19302'}]});let st=await navigator.mediaDevices.getUserMedia({audio:true,video:mode==='video'});document.getElementById('local').srcObject=st;st.getTracks().forEach(t=>pc.addTrack(t,st));pc.ontrack=e=>document.getElementById('remote').srcObject=e.streams[0];pc.onicecandidate=e=>{if(e.candidate)fetch('/api/connect/call/ice/'+callId,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({candidate:e.candidate})}).catch(()=>fail())};pc.onconnectionstatechange=()=>{if(['failed','disconnected'].includes(pc.connectionState))fail()};let offer=await pc.createOffer();await pc.setLocalDescription(offer);await api('/api/connect/call/offer/'+callId,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({offer:offer.sdp})});state.textContent='Ringing…';timer=setInterval(async()=>{if(Date.now()-started>120000){fail();return}try{let x=await api('/api/connect/call/check/'+callId);if(x.call.status==='ended'||x.call.status==='rejected'){fail();return}if(x.call.answer&&!pc.currentRemoteDescription){await pc.setRemoteDescription({type:'answer',sdp:x.call.answer});state.textContent='Connected'}}catch(e){fail()}},1500)}catch(e){fail()}}document.getElementById('hang').onclick=()=>{if(callId)fetch('/api/connect/call/end/'+callId,{method:'POST'});clearInterval(timer);if(pc)pc.close();state.textContent='Call ended'};window.addEventListener('offline',()=>fail());start();</script>''',user_id=user_id,mode=mode,name=_profile_name(user_id))


@app.route('/setup/connect-sql')
def connect_sql():
    return '<pre style="white-space:pre-wrap">'+KOJA_CONNECT_SQL.replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')+'</pre>'


# ============================================================
# PROFESSION-SPECIFIC + PUBLIC COMMUNICATION
# ============================================================

def profession_slug(value):
    import re
    text = clean(value).lower()
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")

def profession_from_slug(slug):
    wanted = profession_slug(slug)
    for item in PROFESSIONAL_CATEGORIES:
        if profession_slug(item) == wanted:
            return item
    return None

PROFESSIONAL_PUBLIC_SQL = r"""
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE TABLE IF NOT EXISTS public.professional_public_messages (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), profession text NOT NULL,
 sender_id uuid NOT NULL, message text NOT NULL, created_at timestamptz DEFAULT now(), deleted_at timestamptz
);
CREATE INDEX IF NOT EXISTS professional_public_messages_profession_idx ON public.professional_public_messages(profession, created_at DESC);
CREATE TABLE IF NOT EXISTS public.professional_public_posts (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), profession text NOT NULL, author_id uuid NOT NULL,
 provider_id uuid, title text NOT NULL, body text NOT NULL, media_url text,
 created_at timestamptz DEFAULT now(), updated_at timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS professional_public_posts_profession_idx ON public.professional_public_posts(profession, created_at DESC);
CREATE TABLE IF NOT EXISTS public.professional_public_comments (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), post_id uuid NOT NULL REFERENCES public.professional_public_posts(id) ON DELETE CASCADE,
 author_id uuid NOT NULL, body text NOT NULL, created_at timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS professional_public_comments_post_idx ON public.professional_public_comments(post_id, created_at);
"""

@app.route("/professional/community/<path:profession_slug>", methods=["GET", "POST"])
def professional_community(profession_slug):
    profession = profession_from_slug(profession_slug)
    if not profession: abort(404)
    me = current_user() or {}
    if request.method == "POST" and not me.get("id"):
        flash("Please log in to participate in public communication.", "warning")
        return redirect(url_for("login", next=request.path))
    if request.method == "POST":
        message = clean(request.form.get("message"))
        if not message:
            flash("Write a message before posting.", "danger")
        else:
            _, error = db_insert("professional_public_messages", {"id":str(uuid.uuid4()),"profession":profession,"sender_id":me.get("id"),"message":message,"created_at":utc_now()})
            if error: flash("Public message could not be sent: " + str(error)[:500], "danger")
        return redirect(url_for("professional_community", profession_slug=profession_slug))
    messages = db_select("professional_public_messages", filters={"profession":profession}, order="created_at.asc", limit=200)
    cache={}
    for m in messages:
        uid=m.get("sender_id")
        if uid not in cache:
            u=first_row("profiles",{"id":uid}) or {}
            cache[uid]=u.get("full_name") or u.get("name") or u.get("email") or "KOJA User"
        m["sender_name"]=cache[uid]
    return render_page(profession+" Communication", r"""
<div class="hero"><h2>💬 {{ profession }} — Public Communication</h2><p>This is the public communication room for <strong>{{ profession }}</strong>. KOJA members can ask questions, share knowledge, make announcements and discuss this profession.</p></div>
<div class="card"><div class="actions"><a class="btn secondary" href="{{ url_for('professionals', category=profession) }}">👥 Find {{ profession }}</a><a class="btn secondary" href="{{ url_for('professional_public_post', profession_slug=profession_slug(profession)) }}">📰 Public Posts</a></div>
<form method="post" style="margin-top:12px"><label>Public message</label><textarea name="message" maxlength="4000" required placeholder="Start a {{ profession }} discussion..."></textarea><button class="btn" type="submit">📢 Send to Public Room</button></form></div>
<div class="card"><h3>🌍 {{ profession }} Public Room</h3>{% for m in messages %}<div style="padding:12px 0;border-bottom:1px solid rgba(127,127,127,.18)"><strong>{{ m.sender_name }}</strong><div style="margin-top:5px;white-space:pre-wrap">{{ m.message }}</div><div class="small">{{ m.created_at }}</div></div>{% else %}<p>No public messages yet. Start the first discussion.</p>{% endfor %}</div>
""", profession=profession, messages=messages)

@app.route("/professional/public-post/<path:profession_slug>", methods=["GET", "POST"])
def professional_public_post(profession_slug):
    profession=profession_from_slug(profession_slug)
    if not profession: abort(404)
    me=current_user() or {}
    if request.method=="POST" and not me.get("id"):
        flash("Please log in to publish a public post.", "warning")
        return redirect(url_for("login", next=request.path))
    if request.method=="POST":
        title=clean(request.form.get("title")); body=clean(request.form.get("body"))
        if not title or not body: flash("Title and message are required.","danger")
        else:
            provider=first_row("service_providers",{"user_id":me.get("id"),"profession":profession})
            _,error=db_insert("professional_public_posts",{"id":str(uuid.uuid4()),"profession":profession,"author_id":me.get("id"),"provider_id":(provider or {}).get("id"),"title":title,"body":body,"created_at":utc_now(),"updated_at":utc_now()})
            if error: flash("Public post could not be published: "+str(error)[:500],"danger")
        return redirect(url_for("professional_public_post",profession_slug=profession_slug))
    posts=db_select("professional_public_posts",filters={"profession":profession},order="created_at.desc",limit=100)
    for post in posts:
        u=first_row("profiles",{"id":post.get("author_id")}) or {}
        post["author_name"]=u.get("full_name") or u.get("name") or u.get("email") or "KOJA User"
    return render_page(profession+" Public Posts", r"""
<div class="hero"><h2>🌍 {{ profession }} — Public Posts</h2><p>Public discussions, announcements, questions and knowledge sharing for {{ profession }}.</p></div>
<div class="card"><form method="post"><label>Post title</label><input name="title" maxlength="180" required placeholder="Discussion or announcement title"><label>Message</label><textarea name="body" maxlength="8000" required placeholder="Write your public post..."></textarea><button class="btn" type="submit">📢 Publish Public Post</button></form></div>
<div class="grid">{% for p in posts %}<div class="card"><h3>{{ p.title }}</h3><p class="small">By {{ p.author_name }} · {{ p.created_at }}</p><p style="white-space:pre-wrap">{{ p.body }}</p></div>{% else %}<div class="card"><p>No public posts yet.</p></div>{% endfor %}</div>
""", profession=profession, posts=posts)

# ============================================================

# ============================================================
# KOJA AFRICA PRODUCTION COMPLETION — MARKETPLACE / DELIVERY / PROFESSIONALS
# ============================================================
PRODUCTION_COMPLETION_SQL = r''' 
ALTER TABLE public.koja_marketplace_products ADD COLUMN IF NOT EXISTS contact_phone text;
ALTER TABLE public.koja_marketplace_products ADD COLUMN IF NOT EXISTS contact_email text;
ALTER TABLE public.koja_marketplace_products ADD COLUMN IF NOT EXISTS whatsapp_number text;
ALTER TABLE public.koja_marketplace_products ADD COLUMN IF NOT EXISTS preferred_contact text default 'KOJA Chat';
ALTER TABLE public.koja_marketplace_products ADD COLUMN IF NOT EXISTS contact_phone_public boolean default false;
ALTER TABLE public.koja_marketplace_products ADD COLUMN IF NOT EXISTS contact_email_public boolean default false;
ALTER TABLE public.koja_marketplace_products ADD COLUMN IF NOT EXISTS whatsapp_public boolean default false;
ALTER TABLE public.koja_marketplace_products ADD COLUMN IF NOT EXISTS location text;
ALTER TABLE public.koja_marketplace_products ADD COLUMN IF NOT EXISTS town text;
ALTER TABLE public.koja_marketplace_products ADD COLUMN IF NOT EXISTS country text;
ALTER TABLE public.koja_marketplace_products ADD COLUMN IF NOT EXISTS continent text;
CREATE TABLE IF NOT EXISTS public.koja_marketplace_actions (id uuid primary key default gen_random_uuid(), order_id uuid, product_id uuid, actor_id uuid not null, action text not null, reason text, created_at timestamptz default now());
CREATE TABLE IF NOT EXISTS public.koja_delivery_proofs (id uuid primary key default gen_random_uuid(), delivery_id uuid not null, uploaded_by uuid not null, proof_url text, proof_type text default 'file', note text, created_at timestamptz default now());
CREATE TABLE IF NOT EXISTS public.professional_reviews (id uuid primary key default gen_random_uuid(), provider_id uuid not null, client_id uuid not null, appointment_id uuid, rating integer not null check(rating between 1 and 5), review text default '', created_at timestamptz default now());
CREATE TABLE IF NOT EXISTS public.professional_payments (id uuid primary key default gen_random_uuid(), appointment_id uuid, client_id uuid not null, provider_id uuid not null, amount numeric(12,2) not null default 0, currency text not null default 'ZMW', status text not null default 'pending', payment_reference text unique, transaction_id text, created_at timestamptz default now(), updated_at timestamptz default now());
'''

def _notify(uid,title,body,ntype='system',related_id=None):
    if not uid:return
    try: db_insert('koja_notifications',{'user_id':uid,'notification_type':ntype,'title':title,'body':body,'related_id':related_id})
    except Exception: pass

def _marketplace_conversation(a,b):
    return _direct_conversation(str(a),str(b)) if a and b and str(a)!=str(b) else None

@app.route('/marketplace/chat/<seller_id>')
@login_required
def marketplace_chat(seller_id):
    me=current_user()['id'];seller=find_user_by_id(seller_id) or {}
    if not seller:abort(404)
    c=_marketplace_conversation(me,seller_id)
    if not c:return 'Unable to create seller conversation. Ensure KOJA Connect SQL is installed.',500
    product_id=clean(request.args.get('product_id'))
    _notify(seller_id,'Marketplace contact',f'{_profile_name(me)} contacted you on KOJA Marketplace.','marketplace',product_id or None)
    return redirect(url_for('connect_chat',conversation_id=c['id']))

@app.route('/marketplace/call/<seller_id>')
@login_required
def marketplace_call(seller_id):
    if str(seller_id)==str(current_user()['id']):return 'You cannot call yourself.',400
    return redirect(url_for('connect_call',user_id=seller_id,mode=clean(request.args.get('mode')) or 'video'))

@app.route('/marketplace/order/<order_id>/<action>',methods=['POST'])
@login_required
def marketplace_order_action(order_id,action):
    me=current_user()['id'];o=first_row('koja_marketplace_orders',{'id':order_id})
    if not o:return 'Order not found.',404
    if str(me) not in {str(o.get('buyer_id')),str(o.get('seller_id'))}:return 'Forbidden',403
    if action not in {'cancel','refund'}:return 'Invalid action',400
    status='cancelled' if action=='cancel' else 'refund_requested';reason=clean(request.form.get('reason')) or action.title()+' requested'
    _,err=db_update('koja_marketplace_orders',{'id':order_id},{'status':status,'updated_at':utc_now()})
    try:db_insert('koja_marketplace_actions',{'order_id':order_id,'product_id':o.get('product_id'),'actor_id':me,'action':action,'reason':reason})
    except Exception:pass
    other=o.get('seller_id') if str(o.get('buyer_id'))==str(me) else o.get('buyer_id')
    _notify(other,'Marketplace order update',f'Order {order_id}: {status}. {reason}','marketplace',order_id)
    flash('Order updated.' if not err else 'Order update failed: '+str(err)[:300],'success' if not err else 'danger')
    return redirect(url_for('marketplace_my'))

@app.route('/marketplace/delivery/<order_id>',methods=['GET','POST'])
@login_required
def marketplace_delivery(order_id):
    me=current_user()['id'];o=first_row('koja_marketplace_orders',{'id':order_id})
    if not o or str(me) not in {str(o.get('buyer_id')),str(o.get('seller_id'))}:return 'Forbidden',403
    product=marketplace_product(o.get('product_id')) or {}
    if request.method=='POST':
        pickup=clean(request.form.get('pickup_address'));dest=clean(request.form.get('delivery_address'))
        if not pickup or not dest:flash('Pickup and delivery addresses are required.','danger')
        else:
            tracking=make_tracking_code();payload={'id':str(uuid.uuid4()),'customer_id':me,'user_id':me,'pickup_address':pickup,'delivery_address':dest,'pickup_location':pickup,'destination':dest,'recipient_name':clean(request.form.get('recipient_name')) or _profile_name(me),'recipient_phone':clean(request.form.get('recipient_phone')),'package_description':'Marketplace order: '+str(product.get('title') or 'Marketplace product'),'delivery_fee':request.form.get('delivery_fee') or 0,'currency':'ZMW','status':'requested','tracking_code':tracking,'created_at':utc_now(),'updated_at':utc_now()}
            row,err=db_insert('deliveries',payload)
            if err:flash('Delivery request failed: '+str(err)[:600],'danger')
            else:
                other=o.get('seller_id') if str(o.get('buyer_id'))==str(me) else o.get('buyer_id');_notify(other,'Marketplace delivery requested',f'Tracking code: {tracking}','delivery',row.get('id') if isinstance(row,dict) else None);flash('Delivery created. Tracking: '+tracking,'success');return redirect(url_for('deliveries'))
    return render_page('Marketplace Delivery',r'''<div class="hero"><h2>🚚 Marketplace Delivery</h2><p>{{ product.title }}</p></div><div class="card"><form method="post"><label>Pickup address</label><input name="pickup_address" required><label>Delivery address</label><input name="delivery_address" required><label>Recipient name</label><input name="recipient_name"><label>Recipient phone</label><input name="recipient_phone"><label>Delivery fee (ZMW)</label><input name="delivery_fee" type="number" min="0" step="0.01" value="0"><button class="btn" type="submit">Create Delivery</button></form></div>''',product=product)

@app.route('/delivery/<delivery_id>/chat')
@login_required
def delivery_chat(delivery_id):
    d=first_row('deliveries',{'id':delivery_id});me=current_user()['id']
    if not d or str(me) not in {str(d.get('customer_id')),str(d.get('user_id')),str(d.get('driver_id'))}:return 'Forbidden',403
    other=d.get('driver_id') if str(me) in {str(d.get('customer_id')),str(d.get('user_id'))} else d.get('customer_id') or d.get('user_id');c=_direct_conversation(me,other)
    if not c:return 'Participant unavailable.',409
    _notify(other,'Delivery message',f'{_profile_name(me)} contacted you about delivery {d.get("tracking_code")}.','delivery',delivery_id)
    return redirect(url_for('connect_chat',conversation_id=c['id']))

@app.route('/delivery/<delivery_id>/call')
@login_required
def delivery_call(delivery_id):
    d=first_row('deliveries',{'id':delivery_id});me=current_user()['id']
    if not d or str(me) not in {str(d.get('customer_id')),str(d.get('user_id')),str(d.get('driver_id'))}:return 'Forbidden',403
    other=d.get('driver_id') if str(me) in {str(d.get('customer_id')),str(d.get('user_id'))} else d.get('customer_id') or d.get('user_id')
    return redirect(url_for('connect_call',user_id=other,mode=clean(request.args.get('mode')) or 'video'))

@app.route('/delivery/<delivery_id>/proof',methods=['GET','POST'])
@login_required
def delivery_proof(delivery_id):
    d=first_row('deliveries',{'id':delivery_id});me=current_user()['id']
    if not d:return 'Delivery not found.',404
    if str(me) not in {str(d.get('customer_id')),str(d.get('user_id')),str(d.get('driver_id'))} and not current_user().get('is_admin'):return 'Forbidden',403
    if request.method=='POST':
        f=request.files.get('proof');note=clean(request.form.get('note'))
        if not f or not f.filename:flash('Choose a proof file.','danger')
        else:
            up,err=upload_storage(f,'delivery/proofs')
            if err:flash('Upload failed: '+str(err)[:500],'danger')
            else:
                _,e=db_insert('koja_delivery_proofs',{'delivery_id':delivery_id,'uploaded_by':me,'proof_url':up.get('url'),'proof_type':'file','note':note})
                if not e:
                    db_update('deliveries',{'id':delivery_id},{'status':'delivered','delivered_at':utc_now(),'updated_at':utc_now()});other=d.get('customer_id') if str(me)==str(d.get('driver_id')) else d.get('driver_id');_notify(other,'Delivery completed','Proof of delivery was uploaded.','delivery',delivery_id);flash('Delivery completed with proof.','success');return redirect(url_for('tracking'))
                flash('Run the production SQL migration first.','danger')
    return render_page('Proof of Delivery',r'''<div class="hero"><h2>📦 Proof of Delivery</h2></div><div class="card"><form method="post" enctype="multipart/form-data"><input type="file" name="proof" required><textarea name="note" placeholder="Delivery note"></textarea><button class="btn success">Upload Proof & Complete</button></form></div>''')

@app.route('/professional/<provider_id>/review',methods=['GET','POST'])
@login_required
def professional_review(provider_id):
    provider=first_row('service_providers',{'id':provider_id});me=current_user()['id']
    if not provider:abort(404)
    if request.method=='POST':
        try:rating=max(1,min(5,int(request.form.get('rating') or 5)))
        except:rating=5
        _,err=db_insert('professional_reviews',{'provider_id':provider_id,'client_id':me,'appointment_id':clean(request.form.get('appointment_id')) or None,'rating':rating,'review':clean(request.form.get('review'))})
        if err:flash('Review could not be saved. Run the production SQL migration first.','danger')
        else:_notify(provider.get('user_id'),'New professional review',f'You received a {rating}/5 review.','professional',provider_id);flash('Review submitted.','success')
    return render_page('Professional Review',r'''<div class="hero"><h2>⭐ Review {{ provider.full_name or provider.name or 'Professional' }}</h2></div><div class="card"><form method="post"><label>Rating</label><select name="rating">{% for n in [5,4,3,2,1] %}<option>{{ n }}</option>{% endfor %}</select><label>Review</label><textarea name="review" maxlength="4000"></textarea><button class="btn">Submit Review</button></form></div>''',provider=provider)

@app.route('/professional/dashboard')
@login_required
def professional_dashboard():
    me=current_user()['id'];p=first_row('service_providers',{'user_id':me})
    if not p:return 'Professional profile not found.',404
    bookings=db_select('appointments',{'provider_id':p.get('id')},order='created_at.desc',limit=100) or [];reviews=db_select('professional_reviews',{'provider_id':p.get('id')},order='created_at.desc',limit=100) or []
    avg=round(sum(int(x.get('rating') or 0) for x in reviews)/len(reviews),1) if reviews else 0
    return render_page('Professional Dashboard',r'''<div class="hero"><h2>👩‍💼 Professional Dashboard</h2><p>{{ p.full_name or p.name }} · {{ p.profession }}</p></div><div class="grid"><div class="card"><h3>Approval</h3><p>{{ p.approval_status or p.verification_status or 'pending' }}</p></div><div class="card"><h3>Bookings</h3><p>{{ bookings|length }}</p></div><div class="card"><h3>Rating</h3><p>⭐ {{ avg }}/5</p></div></div><div class="card"><h3>Recent Bookings</h3>{% for b in bookings[:30] %}<p>{{ b.appointment_type }} · {{ b.appointment_date }} · {{ b.status }} {% if b.status not in ['cancelled','rejected'] %}<form method='post' action='{{ url_for('professional_payment_start',provider_id=p.id,appointment_id=b.id) }}' style='display:inline'><button class='btn secondary'>Pay</button></form>{% endif %} <a class='btn secondary' href='{{ url_for('professional_review',provider_id=p.id) }}'>Review</a></p>{% else %}<p>No bookings yet.</p>{% endfor %}</div><div class="actions"><a class="btn" href="{{ url_for('professional_calls') }}">Calls</a><a class="btn secondary" href="{{ url_for('professional_communication') }}">Communication</a></div>''',p=p,bookings=bookings,reviews=reviews,avg=avg)

@app.route('/professional/<provider_id>/pay/<appointment_id>',methods=['POST'])
@login_required
def professional_payment_start(provider_id,appointment_id):
    if not FLW_SECRET_KEY:return 'Online payment is not configured. Add FLW_SECRET_KEY in Render.',503
    provider=first_row('service_providers',{'id':provider_id});ap=first_row('appointments',{'id':appointment_id});me=current_user()
    if not provider or not ap or str(ap.get('client_id'))!=str(me.get('id')):return 'Forbidden',403
    amount=float(provider.get('hourly_rate') or provider.get('consultation_fee') or 0)
    if amount<=0:return 'Professional fee is not configured.',400
    ref='PRO-'+uuid.uuid4().hex[:24]
    row,err=db_insert('professional_payments',{'appointment_id':appointment_id,'client_id':me['id'],'provider_id':provider_id,'amount':amount,'currency':'ZMW','status':'pending','payment_reference':ref,'created_at':utc_now(),'updated_at':utc_now()})
    if err:return 'Run the production SQL migration first.',500
    try:
        r=requests.post(FLW_BASE_URL+'/payments',headers={'Authorization':'Bearer '+FLW_SECRET_KEY,'Content-Type':'application/json'},json={'tx_ref':ref,'amount':amount,'currency':'ZMW','redirect_url':url_for('professional_payment_callback',_external=True),'customer':{'email':me.get('email') or 'customer@koja.africa','name':me.get('name') or 'KOJA User'},'customizations':{'title':'KOJA Professional Service','description':provider.get('profession') or 'Professional service'}},timeout=30)
        d=r.json() if r.content else {}
        if r.ok and d.get('status')=='success':return redirect(d['data']['link'])
        return jsonify({'error':'Checkout creation failed','details':d}),502
    except Exception as exc:return 'Payment gateway error: '+str(exc)[:300],502

@app.route('/professional/payment/callback')
@login_required
def professional_payment_callback():
    ref=clean(request.args.get('tx_ref'));txid=clean(request.args.get('transaction_id'));p=first_row('professional_payments',{'payment_reference':ref})
    if not p:return 'Payment record not found.',404
    if txid and FLW_SECRET_KEY:
        try:
            r=requests.get(FLW_BASE_URL+'/transactions/'+quote(txid,safe=''),headers={'Authorization':'Bearer '+FLW_SECRET_KEY},timeout=30);d=r.json().get('data') if r.ok else None
            if d and str(d.get('status','')).lower()=='successful' and abs(float(d.get('amount') or 0)-float(p.get('amount') or 0))<0.01 and str(d.get('currency','')).upper()=='ZMW':
                db_update('professional_payments',{'id':p.get('id')},{'status':'paid','transaction_id':txid,'updated_at':utc_now()});_notify(p.get('provider_id'),'Professional payment received','A professional service payment was verified.','payment',p.get('id'));return redirect(url_for('dashboard'))
        except Exception:pass
    if clean(request.args.get('status'))=='cancelled':db_update('professional_payments',{'id':p.get('id')},{'status':'cancelled','updated_at':utc_now()})
    return redirect(url_for('dashboard'))

@app.route('/admin/production-sql')
@admin_required
def production_sql():
    return render_page('Production SQL',r'''<div class="hero"><h2>🛠 Production SQL</h2><p>Run this once in Supabase SQL Editor.</p></div><div class="card"><textarea style="width:100%;min-height:70vh;font-family:monospace">{{ sql }}</textarea></div>''',sql=PRODUCTION_COMPLETION_SQL)

# ERROR HANDLERS
# ============================================================

@app.errorhandler(404)
def not_found(error):
    return render_page("Not Found",r"""
<div class="card"><h2>Page Not Found</h2><p>The requested page does not exist.</p><a class="btn" href="{{ url_for('home') }}">Return Home</a></div>
"""),404

@app.errorhandler(413)
def too_large(error):
    return render_page("File Too Large",r"""
<div class="card"><h2>File Too Large</h2><p>The maximum upload size is {{ max_mb }} MB.</p></div>
""",max_mb=MAX_UPLOAD_MB),413

@app.errorhandler(500)
def internal_error(error):
    logger.exception("Unhandled application error")
    return render_page("Server Error",r"""
<div class="card"><h2>KOJA AFRICA Server Error</h2><p>The server encountered an unexpected error. Check Render logs for details.</p><a class="btn" href="{{ url_for('home') }}">Return Home</a></div>
"""),500

@app.after_request
def security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(self), microphone=(self), geolocation=(self)")
    response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin-allow-popups")
    response.headers.setdefault("X-XSS-Protection", "0")
    if request.is_secure:
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    if request.path.startswith("/api/"):
        response.headers.setdefault("Cache-Control", "no-store")
    response.headers.setdefault("X-KOJA-Version", APP_VERSION)
    return response

@app.before_request
def before_request():
    # Deliberately empty. Never connect to Supabase at startup.
    pass

@app.context_processor
def inject_globals():
    return {"APP_NAME":APP_NAME,"APP_TAGLINE":APP_TAGLINE,"SITE_URL":SITE_URL,"profession_slug":profession_slug}

# ============================================================
# LOCAL / RENDER START
# ============================================================

if __name__=="__main__":
    port=int(os.getenv("PORT","5000"))
    app.run(host="0.0.0.0",port=port,debug=False)

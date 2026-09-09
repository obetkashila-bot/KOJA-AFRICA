import os
import io
import uuid
import math
import secrets
import logging
import smtplib
from email.message import EmailMessage
import json
import hashlib
import hmac
import base64
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from functools import wraps
from urllib.parse import quote, unquote

import requests
from dotenv import load_dotenv
from flask import (
    Flask, request, redirect, url_for, session,
    render_template_string, flash, send_file, jsonify, abort, Response, stream_with_context
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from werkzeug.middleware.proxy_fix import ProxyFix

# Optional document parsers used by KOJA AI file intelligence.
try:
    from pypdf import PdfReader
except Exception:
    PdfReader = None
try:
    from docx import Document as DocxDocument
except Exception:
    DocxDocument = None

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
app.secret_key = os.getenv("SECRET_KEY") or os.getenv("FLASK_SECRET_KEY")
if not app.secret_key:
    raise RuntimeError("SECRET_KEY or FLASK_SECRET_KEY must be configured in production.")
app.config["MAX_CONTENT_LENGTH"] = 15 * 1024 * 1024
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.getenv("SESSION_COOKIE_SECURE", "true").lower() not in ("0", "false", "no")
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=7)
app.config["SESSION_REFRESH_EACH_REQUEST"] = True

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
    os.getenv("SUPABASE_SECRET_KEY", "")
    or os.getenv("SUPABASE_SERVICE_KEY", "")
    or os.getenv("SUPABASE_KEY", "")
)
SUPABASE_PUBLISHABLE_KEY = os.getenv("SUPABASE_PUBLISHABLE_KEY", "")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
FLW_SECRET_KEY = os.getenv("FLW_SECRET_KEY", "").strip()
FLW_SECRET_HASH = os.getenv("FLW_SECRET_HASH", "").strip()
FLW_BASE_URL = "https://api.flutterwave.com/v3"


STORAGE_BUCKET = os.getenv(
    "SUPABASE_STORAGE_BUCKET",
    "koja-files"
)

APP_NAME = "KOJA AFRICA"
APP_VERSION = "2026.09.09-V7-K100M-MONETIZATION-V53-SELLER-CENTER"
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
        "Content-Type": "application/json",
    }
    # New Supabase secret keys are not JWTs. Sending sb_secret_* as
    # Authorization: Bearer causes Invalid JWT; legacy JWT keys still need it.
    if key and not key.startswith("sb_secret_"):
        h["Authorization"] = f"Bearer {key}"
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

def as_bool(value):
    """Safely normalize Supabase boolean-like values from REST responses."""
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() in {"true", "t", "1", "yes", "y", "on"}

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

def safe_next_url(value):
    value=clean(value)
    if not value or not value.startswith('/') or value.startswith('//') or value.startswith('\\'):
        return url_for('home')
    return value

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
    # Do not store Supabase access/refresh tokens in Flask's client-side session cookie.
    # KOJA uses its own authenticated session after Supabase authentication succeeds.
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

    key = SUPABASE_PUBLISHABLE_KEY or SUPABASE_ANON_KEY or SUPABASE_SERVICE_KEY
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

def upload_storage(file_storage, folder="uploads", public=False):
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
        ) if public else None
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
# CSRF PROTECTION
# ============================================================

def csrf_token():
    token = session.get("_csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token
        session.modified = True
    return token

def csrf_valid():
    expected = session.get("_csrf_token")
    supplied = request.form.get("_csrf_token") or request.headers.get("X-CSRF-Token")
    return bool(expected and supplied and secrets.compare_digest(str(expected), str(supplied)))

@app.before_request
def enforce_csrf():
    if request.method not in ("POST", "PUT", "PATCH", "DELETE"):
        return None
    # navigator.sendBeacon() cannot attach the CSRF header. This endpoint is
    # authenticated and only changes the caller's own professional presence.
    if request.path == "/api/professional/presence":
        return None
    # Flutterwave server-to-server webhook is authenticated by its signature, not browser CSRF.
    if request.path == "/webhook/flutterwave":
        return None

    # KOJA Connect WebRTC signaling: keep login + call-participant authorization
    # below, but do not block browser ICE trickling on the page-level CSRF token.
    # These endpoints only operate on calls owned by the authenticated caller/callee.
    if request.path.startswith("/api/connect/call/ice/"):
        return None
    # JSON/browser requests and normal HTML forms are both protected.
    # The token is injected into forms and fetch requests by BASE_HTML.
    if not csrf_valid():
        logger.warning("CSRF validation failed for %s %s", request.method, request.path)
        if request.is_json or request.path.startswith("/api/"):
            return jsonify({"ok": False, "message": "CSRF validation failed. Refresh the page and try again."}), 403
        flash("Security check failed. Please refresh the page and try again.", "danger")
        return redirect(request.referrer or url_for("home"))
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
<meta name="csrf-token" content="{{ csrf_token() }}">
<meta name="theme-color" content="#0b1220">
{% if seo_jsonld %}<script type="application/ld+json">{{ seo_jsonld|safe }}</script>{% endif %}
<title>{{ title or "KOJA AFRICA" }}</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.css">
<script>
(function(){
  var meta=document.querySelector('meta[name="csrf-token"]');
  var token=meta?meta.getAttribute('content'):'';
  var nativeFetch=window.fetch;
  window.fetch=function(input,init){
    init=init||{};
    var method=String(init.method||'GET').toUpperCase();
    if(token && ['POST','PUT','PATCH','DELETE'].indexOf(method)>=0){
      var h=new Headers(init.headers||{});
      if(!h.has('X-CSRF-Token')) h.set('X-CSRF-Token',token);
      init.headers=h;
    }
    return nativeFetch(input,init);
  };
  document.addEventListener('DOMContentLoaded',function(){
    document.querySelectorAll('form').forEach(function(form){
      if(['GET',''].indexOf((form.method||'GET').toUpperCase())===-1 && token && !form.querySelector('input[name="_csrf_token"]')){
        var input=document.createElement('input'); input.type='hidden'; input.name='_csrf_token'; input.value=token; form.appendChild(input);
      }
    });
  });
})();
</script>
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
textarea{min-height:150px;line-height:1.55;resize:vertical} textarea[name="prompt"]{min-height:190px;padding:16px;border-radius:16px;font-size:1rem} textarea[name="q"]{min-height:90px;resize:vertical}
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
<a href="{{ url_for('news_nextgen') }}">📰 News</a>
<a href="{{ url_for('media_nextgen') }}">◉ Media</a>
<a href="{{ url_for('public_videos') }}">🎥 Videos</a>
<a href="{{ url_for('ai_nextgen') }}">✦ AI</a>
<a href="{{ url_for('communication_nextgen') }}">💬 Connect+</a>
<a href="{{ '/market' }}">🛍️ KOJA Market</a><a href="{{ url_for('marketplace') }}">🛒 Digital Marketplace</a>
<a href="{{ url_for('connect') }}">💬 Communication</a>
<a href="{{ url_for('professional_communication') }}">👩‍💼 Professional Communication</a>
<a href="{{ url_for('settings') }}">⚙️ Settings</a>
<div class="menu-group">
<button type="button" id="moreMenuButton" aria-expanded="false" aria-haspopup="true">More ▾</button>
<div class="dropdown" id="moreMenu" role="menu">
<a role="menuitem" href="{{ url_for('deliveries') }}">Deliveries</a>
<a role="menuitem" href="{{ url_for('drivers') }}">Drivers</a>
{% if user.role in ['driver','admin'] or user.is_admin %}<a role="menuitem" href="{{ url_for('driver_dashboard') }}">Driver Dashboard</a>{% endif %}
{% if user and user.is_admin %}<a role="menuitem" href="{{ url_for('admin') }}">Admin</a><a role="menuitem" href="{{ url_for('admin_market') }}">KOJA Market Admin</a><a role="menuitem" href="{{ url_for('admin_marketplace') }}">Digital Marketplace Admin</a>{% endif %}
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
        "Marketplace": "KOJA AFRICA Digital Marketplace — discover and sell digital products.",
        "KOJA Market": "KOJA Market — buy and sell physical and digital products across Africa.",
    }
    # Google-friendly structured data for public pages. This improves entity/page
    # understanding and can enable eligible search enhancements; it does not
    # guarantee a rich result. Private/account pages intentionally get no JSON-LD.
    public_paths = {"/", "/research", "/research/notes", "/marketplace", "/market"}
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
<div class="card"><h3>🧠 KOJA AI</h3><p>Ask KOJA AI for explanations, planning and practical help.</p><a class="btn" href="{{ url_for('ai_assistant') }}">Open KOJA AI</a></div>
<div class="card"><h3>📚 Documents</h3><p>Browse and upload KOJA learning and research documents.</p><a class="btn" href="{{ url_for('documents') }}">Open Documents</a></div>
<div class="card"><h3>🛒 Marketplace</h3><p>Discover digital learning and business resources.</p><a class="btn" href="{{ url_for('marketplace') }}">Marketplace</a></div>
</div>
""")

@app.route("/service-worker.js")
def service_worker():
    # Keep the browser service-worker request valid without changing KOJA page behavior.
    script = """
self.addEventListener('install', function(event) { self.skipWaiting(); });
self.addEventListener('activate', function(event) { event.waitUntil(self.clients.claim()); });
self.addEventListener('fetch', function(event) {
  if (event.request.method !== 'GET') return;
  event.respondWith(fetch(event.request).catch(function() { return new Response('', {status: 503}); }));
});
"""
    return Response(script, mimetype='application/javascript', headers={'Cache-Control':'no-store'})

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
        identifier = clean(request.form.get("identifier") or request.form.get("email")).strip()
        email = identifier.lower()
        password = request.form.get("password","")
        user = find_user_by_email(email)
        if not user and identifier:
            candidates = db_select("profiles", filters={"username": identifier}, limit=1)
            user = candidates[0] if candidates else None
        if not user and identifier:
            candidates = db_select("profiles", filters={"name": identifier}, limit=1)
            user = candidates[0] if candidates else None

        # First: existing KOJA profile password.
        if user and password_matches(user,password):
            if user.get("is_active") is False:
                flash("This account is inactive.","danger")
                return redirect(url_for("login"))
            login_user(user)
            log_activity("login","User logged into KOJA.")
            return redirect(safe_next_url(request.args.get("next")) if request.args.get("next") else url_for("dashboard"))

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
            return redirect(safe_next_url(request.args.get("next")) if request.args.get("next") else url_for("dashboard"))

        flash("Invalid login credentials. Use the same email and password used to create the KOJA account.","danger")
        return redirect(url_for("login"))

    return render_page("Login", r"""
<div class="card" style="max-width:500px;margin:auto">
<h2>KOJA Login</h2>
<p class="small">KOJA supports its local profile password and, when configured, Supabase Auth accounts.</p>
<form method="post">
<label>Email or username</label><input name="identifier" autocomplete="username" required>
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

def research_google(query, limit=8):
    """Google-backed research when a Programmable Search JSON API key/CSE is configured.
    Without credentials, KOJA provides a direct Google Search link instead of scraping Google.
    """
    q=clean(query)
    if not q: return []
    api_key=clean(os.getenv('GOOGLE_SEARCH_API_KEY',''))
    cse_id=clean(os.getenv('GOOGLE_CSE_ID',''))
    if not (api_key and cse_id):
        return [{'source':'Google Search','title':f'Google results for: {q}',
                 'url':'https://www.google.com/search?q='+quote(q),
                 'snippet':'Open Google Search to review live web results for this research query.','year':None,'_google_link':True}]
    try:
        r=requests.get('https://www.googleapis.com/customsearch/v1',
                       params={'key':api_key,'cx':cse_id,'q':q,'num':min(max(limit,1),10)},
                       timeout=5,headers={'User-Agent':'KOJA-AFRICA-Research/7.0'})
        if not r.ok:
            logger.warning('Google research failed status=%s: %s',r.status_code,r.text[:300])
            return []
        out=[]
        for x in r.json().get('items',[]):
            title=clean(x.get('title','')); url=clean(x.get('link',''))
            if title and url:
                out.append({'source':'Google Search','title':title,'url':url,
                            'snippet':clean(x.get('snippet','')),'year':None,'source_type':'website'})
        return out
    except Exception as exc:
        logger.warning('Google research failed: %s',exc)
        return []

def research_web(query, limit=8):
    q=clean(query)
    if not q: return []
    out=[]
    try:
        r=requests.get('https://api.duckduckgo.com/',params={'q':q,'format':'json','no_html':1,'skip_disambig':1},timeout=4,headers={'User-Agent':'KOJA-AFRICA-Research/2.0'})
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
        r=requests.get('https://en.wikipedia.org/w/api.php',params={'action':'query','list':'search','srsearch':q,'srlimit':limit,'format':'json','utf8':1},timeout=4,headers={'User-Agent':'KOJA-AFRICA-Research/2.0'})
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
        r=requests.get('https://api.openalex.org/works',params=params,timeout=5,headers={'User-Agent':'KOJA-AFRICA-Research/6.0'})
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
        r=requests.get('https://api.crossref.org/works',params=params,timeout=5,headers={'User-Agent':'KOJA-AFRICA-Research/6.0'})
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

def _research_normalize_query(query):
    q=clean(query)
    if not q: return ''
    fixes={r"\bassesment\b":"assessment",r"\bassessments\b":"assessments"}
    for pat,repl in fixes.items(): q=re.sub(pat,repl,q,flags=re.I)
    return q

def _research_intent(query):
    q=_research_normalize_query(query).lower().strip()
    if re.search(r'\b(define|definition|meaning|what is|what are|explain)\b',q): return 'definition'
    if re.search(r'\b(compare|comparison|difference|versus|vs)\b',q): return 'comparison'
    if re.search(r'\b(cause|causes|reason|reasons|factors|determinants)\b',q): return 'causes'
    if re.search(r'\b(impact|effect|effects|influence|affect)\b',q): return 'impact'
    if re.search(r'\b(trend|growth|increase|decrease|statistics|data)\b',q): return 'trend'
    return 'general'

def _research_domain(query):
    q=_research_normalize_query(query).lower()
    education_terms=('assessment','assessments','curriculum','teaching','learning','student','school','education','pedagogy','lesson','exam','examination','grading','evaluation','teacher','classroom')
    health_terms=('disease','clinical','patient','doctor','medicine','medical','diagnosis','treatment','nursing','health')
    business_terms=('business','market','sales','customer','profit','company','finance','entrepreneur','marketing')
    science_terms=('matter','energy','atom','atoms','molecule','molecules','element','elements','compound','compounds','force','motion','mass','gravity','physics','chemistry','biology','cell','cells','organism','ecosystem','photosynthesis','electricity','magnetism','particle','particles','matter','radiation','heat','temperature')
    research_terms=('research','methodology','literature review','systematic review','study','sample','qualitative','quantitative')
    if any(x in q for x in education_terms): return 'education'
    if any(x in q for x in health_terms): return 'health'
    if any(x in q for x in business_terms): return 'business'
    if any(x in q for x in science_terms): return 'science'
    if any(x in q for x in research_terms): return 'research'
    return 'general'

def _research_topic_terms(query):
    stop=set('define definition meaning what is what are explain the a an of for in on to and or does do is are can could would should how why which who where when research evidence'.split())
    return [t for t in _research_tokens(_research_normalize_query(query)) if t not in stop]

def _research_query_plan(query):
    """Build a typo-corrected, intent/domain-specific search plan without generic noise."""
    q=_research_normalize_query(query)
    if not q: return []
    intent=_research_intent(q); domain=_research_domain(q)
    topic=' '.join(_research_topic_terms(q)) or q
    plans=[q]
    if intent=='definition':
        if domain=='science': plans.append(f'{topic} definition physics science')
        elif domain=='education': plans.append(f'{topic} definition educational assessment')
        elif domain=='health': plans.append(f'{topic} definition medical clinical')
        elif domain=='business': plans.append(f'{topic} definition business')
        else: plans.append(f'{topic} definition')
    elif intent=='comparison': plans.append(f'{topic} comparison differences evidence')
    elif intent=='causes': plans.append(f'{topic} causes factors evidence')
    elif intent=='impact': plans.append(f'{topic} effects impact evidence')
    elif intent=='trend': plans.append(f'{topic} statistics data trend')
    elif domain=='education': plans.append(f'{topic} educational assessment evidence')
    elif domain=='health': plans.append(f'{topic} clinical evidence guidelines review')
    elif domain=='business': plans.append(f'{topic} business evidence research data')
    elif domain=='science': plans.append(f'{topic} science physics chemistry evidence')
    else: plans.append(f'{topic} research evidence')
    out=[]
    for x in plans:
        x=clean(x)
        if x and x.lower() not in [y.lower() for y in out]: out.append(x)
    return out[:3]

def _research_obviously_irrelevant(r, query):
    title=clean(r.get('title','')).lower(); snippet=clean(r.get('snippet','')).lower()
    source=clean(r.get('source','')).lower()
    intent=_research_intent(query); domain=_research_domain(query)
    topic_terms=_research_topic_terms(query)
    text=title+' '+snippet
    if not title and not snippet: return True
    if r.get('_google_link') or (source=='google search' and 'google.com/search' in clean(r.get('url','')).lower()): return True
    if domain=='science':
        negative_title=('album','song','band','film','movie','novel','war','battle','military','telepathy','mind over','materialism','philosophy','philosophical','plab','licensing','football','sport','game','video game','fiction','character','literature','poem','poetry')
        if any(x in title for x in negative_title): return True
    if intent=='definition' and topic_terms:
        primary=topic_terms[0]
        title_has_primary=bool(primary and re.search(r'\b'+re.escape(primary)+r'\b', title))
        snippet_has_primary=bool(primary and re.search(r'\b'+re.escape(primary)+r'\b', snippet))
        definition_markers=('is defined as','is a','refers to','means','defined as','consists of','is the','are the','is an intrinsic','is a measure')
        has_definition_marker=any(m in snippet for m in definition_markers)
        # Definition searches must be about the requested concept itself. A paper
        # containing the word "mass" in a long title about atherosclerosis, BMI,
        # shootings, etc. is not evidence for "Define mass".
        title_words=re.findall(r"[a-z0-9]+", title)
        compact_title=' '.join(title_words)
        direct_title = compact_title in {primary, f'{primary} physics', f'{primary} chemistry'}
        focused_title = (f'defining {primary}' in compact_title or f'definition of {primary}' in compact_title or f'{primary} definition' in compact_title or compact_title.startswith(primary+' '))
        if source=='wikipedia':
            if not title_has_primary: return True
        elif source in ('openalex','crossref'):
            if not (direct_title or focused_title): return True
            if not has_definition_marker and not focused_title: return True
        elif source in ('web','google search','koja documents'):
            if not title_has_primary and not (snippet_has_primary and has_definition_marker): return True
    return False

def _research_relevance_gate(results, query, minimum=2.15):
    """Strict evidence gate: discard navigation pages, lexical traps and weak topic matches."""
    domain=_research_domain(query); intent=_research_intent(query); q=_research_normalize_query(query).lower()
    topic_terms=list(_research_topic_terms(query));
    domain_terms={
        'education':set('assessment educational education student teacher teaching learning curriculum evaluation grading formative summative diagnostic classroom test examination'.split()),
        'health':set('clinical medical medicine patient health diagnosis treatment disease nursing guideline'.split()),
        'business':set('business market sales customer finance company profit marketing entrepreneurship'.split()),
        'science':set('science scientific physics chemistry biology matter energy atom molecule element compound force motion mass gravity particle radiation heat temperature electricity magnetism'.split()),
        'research':set('research methodology study evidence literature review qualitative quantitative sample'.split()),
        'general':set(),
    }[domain]
    strong=[]
    for r in results:
        if _research_obviously_irrelevant(r,query): continue
        title=clean(r.get('title','')).lower(); snippet=clean(r.get('snippet','')).lower(); text=title+' '+snippet
        source=str(r.get('source','')).lower()
        score=0.0
        topic_hits=sum(1 for t in topic_terms if t in text)
        domain_hits=sum(1 for t in domain_terms if t in text)
        exact_topic=bool(q and q in text)
        primary_exact=bool(topic_terms and topic_terms[0] in title)
        if exact_topic: score+=2.0
        score+=min(topic_hits,6)*0.55
        score+=min(domain_hits,6)*0.25
        if primary_exact: score+=1.0
        if source in ('openalex','crossref'): score+=1.25
        elif source=='koja documents': score+=1.10
        elif source=='wikipedia': score+=0.45
        elif source=='web': score+=0.15
        elif source=='google search': score-=0.75
        if r.get('doi'): score+=0.25
        if r.get('citations'): score+=min(float(r.get('citations') or 0)/200,0.35)
        # Definition questions require direct concept evidence, not just generic keyword overlap.
        if intent=='definition' and topic_terms:
            primary=topic_terms[0]
            direct=primary in title or primary in snippet
            if not direct: continue
            if domain!='general' and domain_hits<1 and source not in ('openalex','crossref','koja documents'): continue
        # Non-general domain research needs actual domain evidence.
        if domain!='general' and domain_hits==0 and not any(t in title for t in topic_terms): continue
        r['_quality_score']=round(score,4)
        if score>=minimum: strong.append(r)
    strong.sort(key=lambda r:(r.get('_quality_score',0),r.get('_logic_score',0),r.get('citations') or 0),reverse=True)
    return strong

def _research_score_logic(results, query):
    """Second-pass evidence ranking: relevance + source quality + freshness + citations."""
    qtokens=set(re.findall(r"[a-z0-9]{3,}",query.lower()))
    quality={'openalex':1.35,'crossref':1.30,'koja documents':1.25,'web':0.75,'wikipedia':0.70,'google search':-0.50}
    now_year=datetime.now(timezone.utc).year
    for r in results:
        text=(clean(r.get('title',''))+' '+clean(r.get('snippet',''))).lower()
        hits=sum(1 for t in qtokens if t in text)
        base=float(r.get('_relevance') or 0)
        source=str(r.get('source','')).lower()
        qscore=quality.get(source,1.0)
        yr=r.get('year')
        freshness=0
        try:
            age=max(0,now_year-int(yr)); freshness=max(0,1-min(age,10)/20)
        except Exception: pass
        cites=min(1.0, float(r.get('citations') or 0)/100)
        r['_logic_score']=round(base + hits*0.12 + qscore + freshness*0.25 + cites*0.20,4)
    return sorted(results,key=lambda r:r.get('_logic_score',0),reverse=True)

def _research_collect(query, year=None, author=None):
    """Run independent evidence sources concurrently so one slow provider does not block all others."""
    plan=_research_query_plan(query)
    jobs=[]
    for q in plan:
        jobs.extend([
            ('google',lambda q=q: research_google(q,6)),
            ('wikipedia',lambda q=q: research_wikipedia(q,4)),
            ('openalex',lambda q=q: research_openalex(q,year,8)),
            ('crossref',lambda q=q: research_crossref(q,year,author,8)),
            ('koja',lambda q=q: research_local_documents(q,8)),
        ])
    raw=[]
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures=[pool.submit(fn) for _,fn in jobs]
        for fut in as_completed(futures):
            try: raw.extend(fut.result() or [])
            except Exception as exc: logger.warning('Research provider task failed: %s',exc)
    results=_research_deduplicate(raw,_research_normalize_query(query))
    ranked=_research_score_logic(results,_research_normalize_query(query))
    return _research_relevance_gate(ranked,_research_normalize_query(query))

def _research_filter(results, source='all', year=None, sort='relevance'):
    source=(source or 'all').lower(); source=source if source in ('all','google','web','wikipedia','academic','koja') else 'all'
    if source!='all':
        if source=='academic': results=[r for r in results if any(x in str(r.get('source','')).lower() for x in ('openalex','crossref'))]
        elif source=='google': results=[r for r in results if 'google search' in str(r.get('source','')).lower()]
        elif source=='koja': results=[r for r in results if 'koja documents' in str(r.get('source','')).lower()]
        else: results=[r for r in results if str(r.get('source','')).lower()==source]
    if year: results=[r for r in results if str(r.get('year') or '')==str(year)]
    if sort=='date': results.sort(key=lambda r:r.get('year') or 0,reverse=True)
    elif sort=='citations': results.sort(key=lambda r:r.get('citations') or 0,reverse=True)
    else: results.sort(key=lambda r:r.get('_relevance',0),reverse=True)
    return results

def _ai_config_status():
    """Return safe Gemini configuration diagnostics without exposing secrets."""
    raw_key=(os.getenv("GEMINI_API_KEY") or "").strip()
    groq_key=(os.getenv("GROQ_API_KEY") or "").strip()
    openai_key=(os.getenv("OPENAI_API_KEY") or "").strip()
    model=(os.getenv("GEMINI_MODEL") or "gemini-3.8-flash").strip()
    fallback=(os.getenv("GEMINI_FALLBACK_MODEL") or "gemini-3.7-flash").strip()
    base=(os.getenv("GEMINI_API_URL") or "https://generativelanguage.googleapis.com/v1beta").strip().rstrip("/")
    endpoint=f"{base}/models/{model}:generateContent"
    return {
        "configured": bool(raw_key),
        "provider": "gemini",
        "endpoint": endpoint,
        "model": model,
        "fallback_model": fallback,
        "key_source": "GEMINI_API_KEY" if raw_key else "none",
        "key_length": len(raw_key),
        "groq_configured": bool(groq_key),
        "groq_model": (os.getenv("GROQ_MODEL") or "groq/compound").strip(),
        "groq_key_source": "GROQ_API_KEY" if groq_key else "none",
        "groq_key_length": len(groq_key),
        "openai_configured": bool(openai_key),
        "openai_model": (os.getenv("OPENAI_MODEL") or "gpt-5").strip(),
        "openai_key_source": "OPENAI_API_KEY" if openai_key else "none",
        "openai_key_length": len(openai_key),
    }

def _ai_model_candidates():
    """Build an ordered, duplicate-free model fallback chain from Render env vars.
    KOJA can survive a retired/unavailable model by trying the next configured model.
    """
    def split_env(name):
        raw=(os.getenv(name) or "").strip()
        return [x.strip() for x in raw.split(",") if x.strip()]
    groq=[]
    groq.extend(split_env("GROQ_MODEL"))
    groq.extend(split_env("GROQ_FALLBACK_MODELS"))
    groq.extend([
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
        "openai/gpt-oss-120b",
        "openai/gpt-oss-20b",
        "qwen/qwen3.6-27b",
        "qwen/qwen3.8-27b",
    ])
    gemini=[]
    gemini.extend(split_env("GEMINI_MODEL"))
    gemini.extend(split_env("GEMINI_FALLBACK_MODELS"))
    gemini.extend([
        "gemini-3.8-flash",
        "gemini-3.7-flash",
        "gemini-3.6-flash",
        "gemini-3.5-flash",
        "gemini-3.5-flash-lite",
    ])
    openai=[]
    openai.extend(split_env("OPENAI_MODEL"))
    openai.extend(split_env("OPENAI_FALLBACK_MODELS"))
    openai.extend(["gpt-5", "gpt-5-mini"])
    def unique(items):
        seen=set(); out=[]
        for x in items:
            if x and x not in seen:
                seen.add(x); out.append(x)
        return out
    return unique(groq), unique(gemini), unique(openai)

def _openai_call(prompt, system_prompt, max_output_tokens=8192, timeout=20):
    """OpenAI Responses API fallback for KOJA AI."""
    api_key=(os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        return "", "missing_openai_api_key"
    _,_,models=_ai_model_candidates()
    for model in models:
        payload={"model":model,"instructions":system_prompt,"input":prompt,"max_output_tokens":max_output_tokens}
        try:
            r=requests.post("https://api.openai.com/v1/responses",json=payload,timeout=(5,min(int(timeout),30)),headers={"Authorization":"Bearer "+api_key,"Content-Type":"application/json"})
            if r.ok:
                data=r.json(); answer=clean(data.get("output_text") or "")
                if not answer:
                    parts=[]
                    for item in data.get("output") or []:
                        for part in item.get("content") or []:
                            if part.get("type")=="output_text" and part.get("text"): parts.append(part["text"])
                    answer=clean("\n".join(parts))
                if answer:return answer,""
            else:
                logger.warning("OpenAI request failed status=%s model=%s",r.status_code,model)
                if r.status_code in (401,403,429): break
        except requests.Timeout:
            logger.warning("OpenAI request timed out model=%s",model)
        except requests.RequestException as exc:
            logger.warning("OpenAI network error model=%s: %s",model,exc)
        except Exception as exc:
            logger.warning("OpenAI response error model=%s: %s",model,exc)
    return "", "openai_provider_error"

def _ai_call(prompt, system_prompt, max_output_tokens=8192, timeout=12, preferred_model=None):
    """Fast normal-chat path: prefer configured Groq, then fall back to Gemini."""
    cfg=_ai_config_status()
    groq_key=(os.getenv("GROQ_API_KEY") or "").strip()
    gemini_key=(os.getenv("GEMINI_API_KEY") or "").strip()
    candidate_groq,candidate_gemini,candidate_openai=_ai_model_candidates()
    preferred_is_gemini=bool(preferred_model and preferred_model in candidate_gemini)
    preferred_is_openai=bool(preferred_model and preferred_model in candidate_openai)

    # Groq is preferred for normal KOJA AI chats when configured because it is
    # optimized for low-latency text generation. Keep the existing Gemini path
    # as a fallback so the application does not depend on one provider.
    if groq_key and not preferred_is_gemini and not preferred_is_openai:
        groq_models=list(candidate_groq)
        if preferred_model and preferred_model in groq_models:
            groq_models=[preferred_model]+[m for m in groq_models if m!=preferred_model]
        for model in groq_models:
            payload={
                "model":model,
                "messages":[{"role":"system","content":system_prompt},{"role":"user","content":prompt}],
                "temperature":0.7,"max_completion_tokens":max_output_tokens,"stream":False,
            }
            try:
                r=requests.post("https://api.groq.com/openai/v1/chat/completions",json=payload,timeout=(5,min(int(timeout),12)),headers={"Authorization":"Bearer "+groq_key,"Content-Type":"application/json"})
                if r.ok:
                    data=r.json(); choices=data.get("choices") or []
                    answer=clean(((choices[0].get("message") or {}).get("content") or "")) if choices else ""
                    if answer: return answer,""
                    logger.warning("Groq returned an empty response model=%s",model)
                else:
                    logger.warning("Groq request failed status=%s model=%s",r.status_code,model)
                    if r.status_code in (401,403,429): break
            except requests.Timeout:
                logger.warning("Groq request timed out model=%s",model)
            except requests.RequestException as exc:
                logger.warning("Groq network error model=%s: %s",model,exc)
            except Exception as exc:
                logger.warning("Groq response error model=%s: %s",model,exc)

    openai_answer, openai_err = ("", "preferred_other_provider") if preferred_is_gemini else _openai_call(prompt, system_prompt, max_output_tokens=max_output_tokens, timeout=min(int(timeout),30))
    if openai_answer:
        return openai_answer, ""

    if not gemini_key:
        return "", "missing_api_key"

    base=(os.getenv("GEMINI_API_URL") or "https://generativelanguage.googleapis.com/v1beta").strip().rstrip("/")
    primary=cfg["model"]; fallback=cfg["fallback_model"]
    payload={
        "systemInstruction":{"parts":[{"text":system_prompt}]},
        "contents":[{"role":"user","parts":[{"text":prompt}]}],
        "generationConfig":{"maxOutputTokens":max_output_tokens,"temperature":0.7},
    }
    headers={"x-goog-api-key":gemini_key,"Content-Type":"application/json"}
    _groq_models, gemini_models, openai_models = _ai_model_candidates()
    models=[]
    for model in ([primary, fallback] + gemini_models):
        if model and model not in models: models.append(model)
    for model in models:
        endpoint=f"{base}/models/{model}:generateContent"
        try:
            r=requests.post(endpoint,json=payload,timeout=(5,min(int(timeout),12)),headers=headers)
            if r.ok:
                data=r.json(); parts=[]
                for candidate in data.get("candidates") or []:
                    for part in (candidate.get("content") or {}).get("parts") or []:
                        if part.get("text"): parts.append(part["text"])
                answer=clean("\n".join(parts))
                if answer: return answer,""
            elif r.status_code in (401,403): return "","authentication_failed"
            elif r.status_code==429: return "","rate_limited"
        except requests.Timeout:
            logger.warning("Gemini request timed out model=%s",model)
            continue
        except requests.RequestException:
            continue
        except Exception:
            continue
    return "","timeout_or_provider_error"

def _ai_stream(prompt, system_prompt, max_output_tokens=32768, timeout=90, preferred_model=None):
    """Stream KOJA AI with multiple live model fallbacks."""
    groq_key=(os.getenv("GROQ_API_KEY") or "").strip()
    if groq_key and not (preferred_model and preferred_model.startswith("gemini-")) and not (preferred_model and preferred_model.startswith("gpt-")):
        groq_models,_gemini_models,_openai_models=_ai_model_candidates()
        for model in groq_models:
            payload={
                "model":model,
                "messages":[{"role":"system","content":system_prompt},{"role":"user","content":prompt}],
                "temperature":0.7,
                "max_completion_tokens":max_output_tokens,
                "stream":True,
            }
            try:
                with requests.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    json=payload, stream=True, timeout=(5,min(int(timeout),90)),
                    headers={"Authorization":"Bearer "+groq_key,"Content-Type":"application/json","Accept":"text/event-stream"},
                ) as r:
                    if not r.ok:
                        logger.warning("Groq streaming failed status=%s model=%s",r.status_code,model)
                        if r.status_code in (401,403,429):
                            break
                        continue
                    got=False
                    for line in r.iter_lines(decode_unicode=True):
                        if not line: continue
                        if isinstance(line,bytes): line=line.decode("utf-8","ignore")
                        if not line.startswith("data:"): continue
                        raw=line[5:].strip()
                        if raw=="[DONE]": break
                        try: data=json.loads(raw)
                        except Exception: continue
                        choices=data.get("choices") or []
                        delta=(choices[0].get("delta") or {}).get("content") if choices else None
                        if delta:
                            got=True; yield {"type":"token","text":delta}
                    if got:
                        yield {"type":"done"}; return
                    logger.warning("Groq streaming returned no text model=%s",model)
            except requests.Timeout:
                logger.warning("Groq streaming timed out model=%s",model)
            except requests.RequestException as exc:
                logger.warning("Groq streaming network error model=%s: %s",model,exc)
            except Exception as exc:
                logger.warning("Groq streaming error model=%s: %s",model,exc)

    # OpenAI streaming fallback.
    openai_key=(os.getenv("OPENAI_API_KEY") or "").strip()
    if openai_key and not (preferred_model and preferred_model.startswith("gemini-")):
        _,_,openai_models=_ai_model_candidates()
        if preferred_model and preferred_model in openai_models:
            openai_models=[preferred_model]+[m for m in openai_models if m!=preferred_model]
        for model in openai_models:
            payload={"model":model,"instructions":system_prompt,"input":prompt,"max_output_tokens":max_output_tokens,"stream":True}
            try:
                with requests.post("https://api.openai.com/v1/responses",json=payload,stream=True,timeout=(5,min(int(timeout),90)),headers={"Authorization":"Bearer "+openai_key,"Content-Type":"application/json","Accept":"text/event-stream"}) as r:
                    if not r.ok:
                        logger.warning("OpenAI streaming failed status=%s model=%s",r.status_code,model)
                        if r.status_code in (401,403,429): break
                        continue
                    got=False
                    for line in r.iter_lines(decode_unicode=True):
                        if not line: continue
                        if isinstance(line,bytes): line=line.decode("utf-8","ignore")
                        if not line.startswith("data:"): continue
                        raw=line[5:].strip()
                        if raw=="[DONE]": break
                        try:data=json.loads(raw)
                        except Exception:continue
                        delta=data.get("delta") if data.get("type")=="response.output_text.delta" else None
                        if delta:
                            got=True; yield {"type":"token","text":delta}
                    if got:
                        yield {"type":"done"}; return
            except requests.Timeout:
                logger.warning("OpenAI streaming timed out model=%s",model)
            except requests.RequestException as exc:
                logger.warning("OpenAI streaming network error model=%s: %s",model,exc)
            except Exception as exc:
                logger.warning("OpenAI streaming error model=%s: %s",model,exc)

    # Final fallback chain. This keeps the browser endpoint responsive even if
    # Groq, OpenAI, or Gemini has a transient failure.
    answer,err=_ai_call(prompt,system_prompt,max_output_tokens=max_output_tokens,timeout=min(int(timeout),12),preferred_model=preferred_model)
    if answer:
        yield {"type":"token","text":answer}; yield {"type":"done"}
    else:
        yield {"type":"error","error":err or "timeout_or_provider_error"}


def _ai_error_message(code):
    return {
        "missing_api_key":"Gemini API key is missing from the running Render service.",
        "authentication_failed":"Gemini rejected the API key. Check that the key is valid and belongs to the configured Google AI project.",
        "endpoint_or_model_not_found":"The Gemini endpoint or model was not found. Check GEMINI_MODEL.",
        "rate_limited":"Gemini rate-limited the request. Wait and try again.",
        "provider_server_error":"Gemini returned a server error. Try again shortly.",
        "timeout":"The Gemini request timed out.",
        "network_error":"KOJA could not reach Gemini from Render.",
        "empty_provider_response":"Gemini returned no usable text.",
        "invalid_provider_response":"KOJA received an unexpected Gemini response format.",
        "safety_blocked":"Gemini blocked the request under its safety policies.",
    }.get(code, "Gemini returned an error. Check the Render logs.")

def _gemini_grounded_research(query, results):
    """Primary KOJA Research synthesis: Gemini + native Google Search grounding.
    Returns (answer, grounded_sources, error_code)."""
    cfg=_ai_config_status()
    api_key=(os.getenv("GEMINI_API_KEY") or "").strip()
    if not api_key:
        return "", [], "missing_api_key"
    base=(os.getenv("GEMINI_API_URL") or "https://generativelanguage.googleapis.com/v1beta").strip().rstrip("/")
    models=[]
    for model in (cfg.get("model"), cfg.get("fallback_model")):
        if model and model not in models: models.append(model)
    intent=_research_intent(query)
    domain=_research_domain(query)
    source_text='\n\n'.join(
        f"LOCAL EVIDENCE [{i+1}] {r.get('title','')} | {r.get('source','')} | {r.get('year') or 'n.d.'}\n"
        f"{clean(r.get('snippet',''))[:1200]}\nURL: {r.get('url','')}"
        for i,r in enumerate(results[:8])
    )
    system=(
        "You are KOJA Research, a rigorous research assistant. "
        "Use Google Search grounding to independently find and verify the best sources for the user's exact question. "
        "Answer the exact question, not merely related topics. For definition questions, define the exact concept requested first. "
        "Prefer authoritative sources, universities, government agencies, professional bodies, peer-reviewed literature and primary sources. "
        "Reject keyword-only matches and unrelated pages. Do not use an album, song, film, fictional work, or unrelated philosophical page as evidence for a scientific definition. "
        "Do not invent facts or citations. Keep the answer concise but useful. "
        "Use numbered source citations [1], [2] immediately after factual claims. "
        "Only cite sources that actually support the claim."
    )
    prompt=(
        f"Research question: {query}\n"
        f"Detected intent: {intent}; domain: {domain}.\n\n"
        "First perform Google Search grounding as needed. Then synthesize the strongest evidence. "
        "The local evidence below is supplementary; do not trust it merely because it contains matching words. "
        "Return a direct answer followed by a short Evidence/Scope note.\n\n"
        f"LOCAL EVIDENCE:\n{source_text or '(none)'}"
    )
    payload={
        "systemInstruction":{"parts":[{"text":system}]},
        "contents":[{"role":"user","parts":[{"text":prompt}]}],
        "tools":[{"google_search":{}}],
        "generationConfig":{"maxOutputTokens":1000,"temperature":0.2},
    }
    headers={"x-goog-api-key":api_key,"Content-Type":"application/json"}
    last_error="provider_server_error"
    for mi,model in enumerate(models):
        try:
            endpoint=f"{base}/models/{model}:generateContent"
            resp=requests.post(endpoint,json=payload,timeout=35,headers=headers)
            if not resp.ok:
                if resp.status_code in (401,403): return "", [], "authentication_failed"
                if resp.status_code==404:
                    last_error="endpoint_or_model_not_found"; continue
                if resp.status_code==429:
                    last_error="rate_limited"; continue
                last_error=f"provider_http_{resp.status_code}"; continue
            data=resp.json()
            cand=(data.get("candidates") or [{}])[0]
            content=cand.get("content") or {}
            parts=content.get("parts") or []
            answer=clean("\n".join(str(x.get("text")) for x in parts if x.get("text")))
            gm=cand.get("groundingMetadata") or {}
            chunks=gm.get("groundingChunks") or []
            grounded=[]
            for i,ch in enumerate(chunks):
                web=ch.get("web") or {}
                url=clean(web.get("uri"))
                title=clean(web.get("title")) or url
                if not url: continue
                grounded.append({"title":title,"url":url,"source":"Google Search","snippet":"Google-grounded source supporting KOJA Research.","year":None,"citations":0,"_grounded_index":i})
            if answer:
                return answer, grounded, ""
            last_error="empty_provider_response"
        except requests.Timeout:
            last_error="timeout"
        except requests.RequestException:
            last_error="network_error"
        except Exception as exc:
            logger.warning("Grounded research parsing failed: %s",exc)
            last_error="invalid_provider_response"
    return "", [], last_error


def _groq_grounded_research(query, results):
    """Fallback KOJA Research synthesis using Groq Compound web search."""
    api_key=(os.getenv("GROQ_API_KEY") or "").strip()
    if not api_key: return "", "missing_groq_api_key"
    model=(os.getenv("GROQ_MODEL") or "groq/compound").strip()
    intent=_research_intent(query); domain=_research_domain(query)
    local='\n\n'.join(f"LOCAL EVIDENCE [{i+1}] {r.get('title','')} | {r.get('source','')} | {r.get('year') or 'n.d.'}\n{clean(r.get('snippet',''))[:1000]}\nURL: {r.get('url','')}" for i,r in enumerate(results[:8]))
    system=("You are KOJA Research, a rigorous research assistant. Answer the exact research question. For definition questions, define the exact concept first. Use your built-in web search to verify information when needed. Prefer universities, government agencies, professional bodies, peer-reviewed literature and primary sources. Reject keyword-only or unrelated matches. Do not invent facts or citations. Use numbered source citations [1], [2] only when the source actually supports the claim. Return a direct answer followed by a concise Evidence/Scope note.")
    prompt=f"Research question: {query}\nDetected intent: {intent}; domain: {domain}.\n\nLOCAL EVIDENCE (supplementary):\n{local or '(none)'}"
    payload={"model":model,"messages":[{"role":"system","content":system},{"role":"user","content":prompt}],"temperature":0.2,"max_completion_tokens":1000}
    try:
        resp=requests.post("https://api.groq.com/openai/v1/chat/completions",json=payload,timeout=35,headers={"Authorization":f"Bearer {api_key}","Content-Type":"application/json"})
        if not resp.ok:
            if resp.status_code in (401,403): return "", "groq_authentication_failed"
            if resp.status_code==429: return "", "groq_rate_limited"
            return "", f"groq_http_{resp.status_code}"
        data=resp.json(); choices=data.get("choices") or []
        answer=clean(((choices[0].get("message") or {}).get("content") or "")) if choices else ""
        return (answer, "") if answer else ("", "groq_empty_response")
    except requests.Timeout: return "", "groq_timeout"
    except requests.RequestException: return "", "groq_network_error"
    except Exception: return "", "groq_invalid_response"


def research_ai_summary(query, results):
    if not query: return '', []
    answer, grounded, error=_gemini_grounded_research(query, results)
    if answer:
        return answer, grounded
    groq_answer, groq_error=_groq_grounded_research(query, results)
    if groq_answer:
        return groq_answer, []
    # Deterministic fallback: never call a loose snippet concatenation a synthesized AI answer.
    # Do not turn a rate-limit event into a misleading list of loosely related
    # search snippets. The relevance gate above is the last line of defence.
    if not results:
        return ("AI research synthesis is temporarily unavailable. " + _ai_error_message(error) +
                "\n\nNo sufficiently relevant evidence passed KOJA's research-quality filter."), []
    highlights=[]
    for r in results[:2]:
        ss=clean(r.get('snippet','')).replace('\n',' ')
        if ss: highlights.append(f"{r.get('title','Source')}: {ss[:500]}")
    fallback=("AI research synthesis is temporarily unavailable. " + _ai_error_message(error) +
              "\n\nVerified relevant evidence:\n\n" + '\n\n'.join(highlights))
    return fallback, []


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
    text=_gemini_text(prompt,'You are KOJA Research Notes. Be evidence-bound, clear, academic and concise. Never fabricate citations or source details.',2200,20)
    if text: return text
    lines=[f"# Research Notes: {query}","","## Introduction",f"The search retrieved {len(results)} relevant records. The notes below are limited to the evidence contained in those records.",""]
    for i,r in enumerate(results[:8],1):
        evidence=clean(r.get('snippet',''))
        if evidence: lines += [f"## {i}. {r.get('title','Untitled')} [{i}]",evidence,""]
    lines += ["## Conclusion","The available evidence is source-dependent and should be checked against the original publications before formal submission."]
    return '\n'.join(lines)


@app.route('/research/notes')
def research_notes():
    q=_research_normalize_query(request.args.get('q','')); style=clean(request.args.get('style','apa')).lower() or 'apa'
    if style not in CITATION_STYLES: style='apa'
    results=[]
    if q:
        results=_research_collect(q)[:12]
    notes=research_ai_notes(q,results,style) if q else ''
    bibliography=make_bibliography(results,style) if results else []
    return render_page('Research Notes', r'''<style>
.notes-shell{max-width:1000px;margin:auto}.notes-toolbar{display:grid;grid-template-columns:1fr auto auto;gap:10px}.notes-body{line-height:1.8;font-size:1rem}.notes-body pre{white-space:pre-wrap;font:inherit}.ref{margin:10px 0}.note-actions{display:flex;gap:8px;flex-wrap:wrap;margin:12px 0}@media(max-width:700px){.notes-toolbar{grid-template-columns:1fr}.notes-body{font-size:.97rem}}
</style><div class="notes-shell"><div class="hero"><h2>📝 KOJA Research Notes</h2><p>Turn ranked research evidence into clear, connected academic notes.</p><form method="get" action="{{ url_for('research_notes') }}" class="notes-toolbar"><input name="q" value="{{ q }}" placeholder="Enter your research topic…" required><select name="style">{% for k,v in citation_styles.items() %}<option value="{{k}}" {% if style==k %}selected{% endif %}>{{v}}</option>{% endfor %}</select><button class="btn">Write Notes</button></form></div>{% if q %}<div class="note-actions"><button class="btn secondary" type="button" onclick="copyKOJANotes()">Copy Notes</button><button class="btn secondary" type="button" onclick="window.print()">Print</button><a class="btn secondary" href="{{ url_for('research',q=q,style=style) }}">View Evidence</a></div><div class="card"><strong>{{ results|length }} ranked evidence sources</strong></div><div id="koja-notes" class="card notes-body"><pre>{{ notes }}</pre></div>{% if bibliography %}<div class="card"><h3>References</h3>{% for n,ref in bibliography %}<div class="ref">{{ n }}. {{ ref|safe }}</div>{% endfor %}</div>{% endif %}<script>function copyKOJANotes(){const el=document.getElementById('koja-notes');navigator.clipboard.writeText(el.innerText).then(()=>alert('Research notes copied.')).catch(()=>alert('Select and copy the notes manually.'))}</script>{% else %}<div class="card"><h3>How KOJA writes notes</h3><p>1. Searches multiple evidence sources.</p><p>2. Removes duplicates and ranks relevance.</p><p>3. Gives the AI only the strongest evidence.</p><p>4. Produces connected academic paragraphs with source citations.</p><p>5. Generates a bibliography in your selected citation style.</p></div>{% endif %}</div>''',q=q,style=style,citation_styles=CITATION_STYLES,results=results,notes=notes,bibliography=bibliography)

@app.route('/research')
def research():
    q=_research_normalize_query(request.args.get('q','')); source_filter=clean(request.args.get('source','all')).lower() or 'all'; sort=clean(request.args.get('sort','relevance')).lower() or 'relevance'; year=_research_year(request.args.get('year','')); author=clean(request.args.get('author','')); style=clean(request.args.get('style','apa')).lower() or 'apa'; source_type=clean(request.args.get('source_type','all')).lower() or 'all'
    if style not in CITATION_STYLES: style='apa'
    results=[]
    if q:
        results=_research_collect(q,year,author)
        results=_research_filter(results,source_filter,year,sort)
        if source_type!='all': results=[r for r in results if _source_type(r)==source_type]
    summary, grounded_sources=research_ai_summary(q,results) if q else ('', [])
    if grounded_sources:
        # Grounded Google sources become the primary visible evidence; retain only a few
        # highly relevant KOJA/academic records as supplementary context.
        existing=[r for r in results if str(r.get('source','')).lower() in ('openalex','crossref','koja documents')][:4]
        results=grounded_sources + existing
    bibliography=make_bibliography(results,style) if results else []
    return render_page('Research', r'''
<style>
.research-shell{max-width:920px;margin:auto}.research-search{display:flex;flex-direction:column;gap:8px;background:rgba(127,127,127,.08);border:1px solid rgba(127,127,127,.18);padding:10px 12px;border-radius:24px}.research-search textarea{width:100%;min-width:0;resize:none;min-height:105px;max-height:280px;border:0!important;background:transparent!important;box-shadow:none!important;font-size:1.05rem;padding:14px 10px!important;outline:none}.research-composer-bottom{display:flex;align-items:center;gap:8px}.research-composer-actions{display:flex;align-items:center;gap:6px}.research-icon{width:42px!important;height:42px!important;margin:0!important;padding:0!important;border-radius:50%!important;display:inline-flex!important;align-items:center;justify-content:center;font-size:1.2rem;cursor:pointer}.research-send{margin-left:auto!important;width:44px!important;height:44px!important;border-radius:50%!important;padding:0!important;display:inline-flex!important;align-items:center;justify-content:center;font-size:1.15rem}.research-file-name{font-size:.78rem;opacity:.72;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:55%}.research-recording{font-size:.78rem;font-weight:700;display:none}.research-search .btn{border-radius:22px;padding:10px 18px}.research-filters{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-top:14px}.research-filters label{font-size:.78rem;font-weight:700;opacity:.9}.research-filters select,.research-filters input{width:100%;margin-top:5px}.research-tabs{display:flex;gap:8px;overflow:auto;margin:14px 0;padding-bottom:2px}.research-tabs a{white-space:nowrap;border-radius:20px}.source-badge{display:inline-block;padding:5px 10px;border-radius:999px;background:rgba(80,150,255,.14);font-size:.74rem;font-weight:800}.research-result{border-radius:18px!important;margin-bottom:12px}.research-result h3{line-height:1.35;margin:9px 0}.research-result h3 a{text-decoration:none}.research-meta{font-size:.82rem;opacity:.72}.research-summary{border:1px solid rgba(98,168,255,.28);border-radius:18px!important;background:rgba(98,168,255,.06)}.research-summary pre{white-space:pre-wrap;font:inherit;line-height:1.7;margin:0}.research-count{font-weight:700}.research-empty{padding:35px;text-align:center;border-radius:18px!important}.research-welcome{text-align:center;padding:20px 10px 8px}.research-welcome h2{font-size:1.8rem;margin-bottom:8px}.research-welcome p{opacity:.75}.research-answer-label{font-weight:800;margin-bottom:10px}.research-source-list{margin-top:6px}.research-source-list .card{border-radius:18px!important}@media(max-width:700px){.research-search{border-radius:18px}.research-filters{grid-template-columns:1fr 1fr}.research-result{padding:16px!important}}@media(max-width:480px){.research-filters{grid-template-columns:1fr}}
</style>
<div class="research-shell"><div class="research-welcome"><h2>🔎 What would you like to research?</h2><p>Ask a full question, attach a document, or use your voice. KOJA Research searches web, academic literature, Wikipedia and your KOJA documents, then brings the evidence together.</p></div><div class="hero"><form method="get" action="{{ url_for('research') }}" class="research-search" id="research-composer"><textarea name="q" rows="3" maxlength="2000" placeholder="Ask anything you want to research…" aria-label="Research question" autofocus>{{ q }}</textarea><div class="research-composer-bottom"><div class="research-composer-actions"><label class="btn secondary research-icon" title="Attach a document" aria-label="Attach a document">📎<input id="research-file" type="file" accept=".pdf,.doc,.docx,.txt,.jpg,.jpeg,.png,.webp" hidden></label><button class="btn secondary research-icon" id="research-record" type="button" title="Record voice" aria-label="Record voice">🎙️</button><span class="research-recording" id="research-recording">● Recording…</span><span class="research-file-name" id="research-file-name"></span></div><button class="btn research-send" type="submit" title="Send research question" aria-label="Send research question">➤</button></div></form>
<script>(function(){const box=document.querySelector('#research-composer textarea[name="q"]');const file=document.getElementById('research-file');const name=document.getElementById('research-file-name');const rec=document.getElementById('research-record');const recLabel=document.getElementById('research-recording');let media=null,chunks=[];if(box){const grow=()=>{box.style.height='auto';box.style.height=Math.min(box.scrollHeight,280)+'px'};box.addEventListener('input',grow);grow()}if(file){file.addEventListener('change',()=>{name.textContent=file.files&&file.files[0]?file.files[0].name:''})}if(rec&&navigator.mediaDevices&&window.MediaRecorder){rec.addEventListener('click',async()=>{if(media){media.stop();return}try{const stream=await navigator.mediaDevices.getUserMedia({audio:true});media=new MediaRecorder(stream);chunks=[];media.ondataavailable=e=>{if(e.data.size)chunks.push(e.data)};media.onstop=()=>{const blob=new Blob(chunks,{type:'audio/webm'});const url=URL.createObjectURL(blob);name.textContent='Voice recording ready ('+Math.round(blob.size/1024)+' KB)';const a=document.createElement('a');a.href=url;a.download='koja-research-question.webm';a.style.display='none';document.body.appendChild(a);a.click();setTimeout(()=>{URL.revokeObjectURL(url);a.remove()},1000);stream.getTracks().forEach(t=>t.stop());media=null;rec.textContent='🎙️';recLabel.style.display='none'};media.start();rec.textContent='⏹️';recLabel.style.display='inline';}catch(e){alert('Microphone permission is required to record.')}})}})();</script><div class="research-filters"><label>Source<select name="source" form="research-filter-form"><option value="all" {% if source_filter=='all' %}selected{% endif %}>All sources</option><option value="academic" {% if source_filter=='academic' %}selected{% endif %}>Academic</option><option value="web" {% if source_filter=='web' %}selected{% endif %}>Web</option><option value="wikipedia" {% if source_filter=='wikipedia' %}selected{% endif %}>Wikipedia</option><option value="koja" {% if source_filter=='koja' %}selected{% endif %}>KOJA Documents</option></select></label><label>Year<input name="year" form="research-filter-form" value="{{ year or '' }}" placeholder="e.g. 2025" inputmode="numeric"></label><label>Author<input name="author" form="research-filter-form" value="{{ author }}" placeholder="Academic author"></label><label>Citation style<select name="style" form="research-filter-form">{% for k,v in citation_styles.items() %}<option value="{{k}}" {% if style==k %}selected{% endif %}>{{v}}</option>{% endfor %}</select></label><label>Source type<select name="source_type" form="research-filter-form"><option value="all">All source types</option>{% for k,v in source_types.items() %}<option value="{{k}}" {% if source_type==k %}selected{% endif %}>{{v}}</option>{% endfor %}</select></label><label>Sort<select name="sort" form="research-filter-form"><option value="relevance" {% if sort=='relevance' %}selected{% endif %}>Relevance</option><option value="date" {% if sort=='date' %}selected{% endif %}>Newest first</option><option value="citations" {% if sort=='citations' %}selected{% endif %}>Most cited</option></select></label></div><form id="research-filter-form" method="get" action="{{ url_for('research') }}"><input type="hidden" name="q" value="{{ q }}"></form></div>
{% if q %}<div class="note-actions"><a class="btn" href="{{ url_for('research_notes',q=q,style=style) }}">📝 Write Research Notes</a><a class="btn secondary" href="{{ url_for('research') }}">＋ New research</a></div><div class="research-tabs"><a class="btn secondary" href="{{ url_for('research',q=q,source='all',sort=sort,year=year,author=author) }}">All</a><a class="btn secondary" href="{{ url_for('research',q=q,source='academic',sort=sort,year=year,author=author) }}">🎓 Academic</a><a class="btn secondary" href="{{ url_for('research',q=q,source='web',sort=sort,year=year,author=author) }}">🌐 Web</a><a class="btn secondary" href="https://www.google.com/search?q={{ q|urlencode }}" target="_blank" rel="noopener">🔎 Google</a><a class="btn secondary" href="{{ url_for('research',q=q,source='koja',sort=sort,year=year,author=author) }}">📁 KOJA Documents</a></div><div class="card"><span class="research-count">{{ results|length }} ranked sources</span> found for <strong>“{{ q }}”</strong><p class="small" style="margin-top:8px">KOJA combines multiple research angles, academic literature, web sources and KOJA Documents; it removes duplicates, filters weak matches, ranks evidence and then uses KOJA AI to synthesize the strongest evidence.</p></div>{% if summary %}<div class="card research-summary"><div class="research-answer-label">🧠 KOJA Research Answer</div><pre>{{ summary }}</pre><p class="small">AI summaries use configured AI credentials when available; otherwise KOJA shows source-based highlights. Verify important claims against original sources.</p></div>{% endif %}{% for r in results %}<div class="card research-result"><span class="source-badge">{{ r.source }}</span><h3><a href="{{ r.url or '#' }}" {% if r.url %}target="_blank" rel="noopener noreferrer"{% endif %}>{{ r.title }}</a></h3>{% if r.year or r.citations %}<p class="research-meta">{% if r.year %}{{ r.year }}{% endif %}{% if r.citations %} • {{ r.citations }} citations{% endif %}</p>{% endif %}<p>{{ r.snippet }}</p><p><strong>In-text:</strong> {{ make_intext(r,style,loop.index) }}</p>{% if r.url %}<a class="btn secondary" href="{{ r.url }}" target="_blank" rel="noopener noreferrer">Open original source ↗</a>{% endif %}</div>{% else %}<div class="card research-empty"><h3>No matching results</h3><p>Try a broader question, remove the year/author filter, or search another source.</p></div>{% endfor %}{% if bibliography %}<div class="card"><h2>References</h2><p class="small">Generated from available source metadata. Verify against the original source.</p>{% for n,ref in bibliography %}<p style="padding-left:28px;text-indent:-28px;line-height:1.6">{{ ref|safe }}</p>{% endfor %}</div>{% endif %}{% else %}<div class="grid"><div class="card"><h3>🔎 Research Discovery</h3><p>KOJA searches across multiple research sources and filters weak or unrelated matches.</p></div><div class="card"><h3>🎓 Academic Search</h3><p>OpenAlex and Crossref provide scholarly metadata, authors, years and citation information.</p></div><div class="card"><h3>📁 KOJA Documents</h3><p>Search documents already connected to your KOJA Supabase database.</p></div><div class="card"><h3>🧠 AI Research Summary</h3><p>Configure an AI API key to synthesize retrieved evidence with source-number citations.</p></div></div>{% endif %}</div>
''',q=q,results=results,summary=summary,source_filter=source_filter,sort=sort,year=year,author=author,style=style,source_type=source_type,citation_styles=CITATION_STYLES,source_types=SOURCE_TYPES,bibliography=bibliography,make_intext=make_intext,SITE_URL=SITE_URL)


@app.route("/api/ai/status")
@login_required
def ai_status():
    """Safe runtime AI diagnostics. Never returns the API key itself."""
    cfg=_ai_config_status()
    return jsonify({
        "status":"configured" if cfg["configured"] else "missing_key",
        "provider":cfg["provider"],
        "model":cfg["model"],
        "endpoint":cfg["endpoint"],
        "key_source":cfg["key_source"],
        "key_length":cfg["key_length"],
        "hint":"Render environment changes require a deploy before the running service can use them." if not cfg["configured"] else "Runtime key detected. Use KOJA AI to perform a live provider test."
    })


@app.route("/ai", methods=["GET", "POST"])
@login_required
def ai_assistant():
    """KOJA AI 2.0: persistent conversations stored server-side in Supabase."""
    user = current_user() or {}
    uid = str(user.get("id") or "")
    conversations = db_select("koja_ai_conversations", {"user_id": uid, "is_archived": False}, order="updated_at.desc", limit=30)
    conversation_id = clean(request.args.get("conversation_id"))
    if request.method == "POST":
        action = clean(request.form.get("action", "chat"))
        conversation_id = clean(request.form.get("conversation_id") or conversation_id)
        if action == "new":
            row, err = db_insert("koja_ai_conversations", {"user_id": uid, "title": "New KOJA AI chat"})
            if row and row.get("id"):
                return redirect(url_for("ai_assistant", conversation_id=row["id"]))
            flash("Could not create a new AI chat. Run KOJA_AI_V2_SQL.sql in Supabase first.", "danger")
            return redirect(url_for("ai_assistant"))
        if action == "archive":
            if conversation_id:
                db_update("koja_ai_conversations", {"id": conversation_id, "user_id": uid}, {"is_archived": True, "updated_at": utc_now()})
            return redirect(url_for("ai_assistant"))
        prompt = clean(request.form.get("prompt"))
        if not prompt:
            flash("Enter a question for KOJA AI.", "warning")
            return redirect(url_for("ai_assistant", conversation_id=conversation_id) if conversation_id else url_for("ai_assistant"))
        if _rate_limited("ai:" + uid, 20, 300):
            flash("Too many AI requests. Please wait a few minutes.", "warning")
            return redirect(url_for("ai_assistant", conversation_id=conversation_id) if conversation_id else url_for("ai_assistant"))
        if not conversation_id:
            row, err = db_insert("koja_ai_conversations", {"user_id": uid, "title": prompt[:80] or "New KOJA AI chat"})
            if row and row.get("id"):
                conversation_id = row["id"]
            else:
                flash("KOJA AI storage is not ready. Run KOJA_AI_V2_SQL.sql in Supabase.", "danger")
                return redirect(url_for("ai_assistant"))
        owned = db_select("koja_ai_conversations", {"id": conversation_id, "user_id": uid, "is_archived": False}, limit=1)
        if not owned:
            flash("That AI conversation is unavailable.", "danger")
            return redirect(url_for("ai_assistant"))
        previous = db_select("koja_ai_messages", {"conversation_id": conversation_id, "user_id": uid}, order="created_at.desc", limit=20)
        previous.reverse()
        context_lines = []
        for item in previous:
            role = "USER" if item.get("role") == "user" else "KOJA AI"
            context_lines.append(role + ": " + clean(item.get("content"))[:12000])
        # Give repeated questions natural variation while keeping the factual core stable.
        response_styles = [
            "Answer directly in a concise conversational style.",
            "Answer in a slightly different natural wording, with the key point first.",
            "Explain it simply and practically, using a short example only when useful.",
            "Give a compact answer with the most important details first.",
            "Use a clear, friendly explanation with different wording from a previous answer if the question repeats.",
        ]
        response_style = secrets.choice(response_styles)
        system = (
            "You are KOJA AI, the general AI assistant inside KOJA AFRICA. Answer clearly and practically. "
            "Do not invent citations, facts, names, prices, laws, medical diagnoses, or current events. "
            "If information is uncertain or requires live verification, say so. Maintain continuity using the supplied conversation. "
            "When the user asks the same or nearly the same question again, vary the wording, structure, examples, or level of explanation naturally, "
            "but keep the underlying facts, conclusion, and important numbers consistent. Never change a fact merely to sound different. "
            "Avoid repetitive stock openings and do not mention that you are varying the response. "
            "" + response_style + " "
            "KOJA has separate Research, Documents, Assignments, Professional Services, Marketplace and Delivery modules. "
            "When the user asks for research, recommend the KOJA Research Engine rather than pretending you browsed the web."
        )
        full_prompt = "Conversation history:\n" + ("\n".join(context_lines) if context_lines else "(none)") + "\n\nUSER: " + prompt
        answer, ai_error = _ai_call(full_prompt, system, max_output_tokens=1200, timeout=20)
        if not answer:
            flash("KOJA AI: " + _ai_error_message(ai_error), "danger")
        else:
            db_insert("koja_ai_messages", {"conversation_id": conversation_id, "user_id": uid, "role": "user", "content": prompt})
            db_insert("koja_ai_messages", {"conversation_id": conversation_id, "user_id": uid, "role": "assistant", "content": answer})
            title = clean(owned[0].get("title"))
            update = {"updated_at": utc_now()}
            if not title or title == "New KOJA AI chat":
                update["title"] = prompt[:80] or "New KOJA AI chat"
            db_update("koja_ai_conversations", {"id": conversation_id, "user_id": uid}, update)
            log_activity("ai_chat", "User used KOJA AI 2.0.")
        return redirect(url_for("ai_assistant", conversation_id=conversation_id))

    messages = []
    if conversation_id:
        owned = db_select("koja_ai_conversations", {"id": conversation_id, "user_id": uid, "is_archived": False}, limit=1)
        if not owned:
            conversation_id = ""
        else:
            messages = db_select("koja_ai_messages", {"conversation_id": conversation_id, "user_id": uid}, order="created_at.asc", limit=100)
    return render_page("KOJA AI", r'''
<style>
.koja-ai-page{position:relative;width:calc(100% + 24px);min-height:calc(100vh - 70px);margin:-8px -12px 0;display:flex;flex-direction:column;background:var(--bg,#fff)}
.koja-ai-top{height:58px;display:flex;align-items:center;gap:8px;padding:8px 14px;border-bottom:1px solid rgba(127,127,127,.18);position:sticky;top:0;z-index:20;background:var(--bg,#fff)}
.koja-ai-icon{width:42px;height:42px;display:inline-flex;align-items:center;justify-content:center;border:1px solid rgba(127,127,127,.22);border-radius:12px;background:transparent;font-size:20px;cursor:pointer;text-decoration:none;color:inherit}
.koja-ai-title{font-weight:700;font-size:16px;margin-right:auto}.koja-ai-main{width:100%;max-width:1100px;margin:0 auto;flex:1;display:flex;flex-direction:column;padding:18px 18px 26px;box-sizing:border-box}.koja-ai-messages{flex:1;padding:8px 0 18px}.koja-ai-empty{min-height:55vh;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center}.koja-ai-empty h2{font-size:30px;margin:0 0 8px}.koja-ai-empty p{opacity:.7}.koja-ai-msg{display:flex;margin:20px 0}.koja-ai-msg.user{justify-content:flex-end}.koja-ai-bubble{max-width:min(78%,720px);padding:13px 16px;border-radius:18px;line-height:1.55;white-space:pre-wrap;overflow-wrap:anywhere}.koja-ai-msg.user .koja-ai-bubble{background:rgba(127,127,127,.16);border-bottom-right-radius:6px}.koja-ai-msg.assistant .koja-ai-bubble{border-bottom-left-radius:6px}.koja-ai-compose{position:sticky;bottom:0;padding-top:8px;background:linear-gradient(transparent,var(--bg,#fff) 18%)}.koja-ai-compose{padding-bottom:env(safe-area-inset-bottom)}.koja-ai-compose form{display:flex;flex-direction:column;gap:6px;border:1px solid rgba(127,127,127,.28);border-radius:24px;padding:10px 10px 8px 14px;background:var(--bg,#fff);box-shadow:0 2px 12px rgba(0,0,0,.05)}.koja-ai-input-row{display:flex;align-items:flex-end;gap:8px}.koja-ai-compose textarea{border:0!important;box-shadow:none!important;outline:none!important;resize:none;min-height:34px;max-height:180px;margin:0!important;padding:8px 0!important;background:transparent!important;flex:1;font-size:16px;line-height:1.45}.koja-ai-tools{display:flex;align-items:center;gap:4px}.koja-ai-tool{width:38px;height:38px;border:0;border-radius:50%;cursor:pointer;background:transparent;color:inherit;font-size:20px;display:inline-flex;align-items:center;justify-content:center}.koja-ai-tool:hover{background:rgba(127,127,127,.12)}.koja-ai-tool.recording{background:rgba(220,60,60,.15)}.koja-ai-send{width:42px;height:42px;border:0;border-radius:50%;cursor:pointer;font-size:18px}.koja-ai-file{display:none}.koja-ai-attachment{display:none;align-items:center;gap:8px;margin:2px 2px 0;padding:7px 10px;border-radius:12px;background:rgba(127,127,127,.10);font-size:.86rem}.koja-ai-attachment.show{display:flex}.koja-ai-attachment button{margin-left:auto;border:0;background:transparent;cursor:pointer;font-size:17px;color:inherit}.koja-ai-drawer{position:fixed;inset:0;z-index:100;display:none}.koja-ai-drawer.open{display:block}.koja-ai-backdrop{position:absolute;inset:0;background:rgba(0,0,0,.38)}.koja-ai-panel{position:absolute;left:0;top:0;bottom:0;width:min(320px,86vw);padding:14px;background:var(--bg,#fff);box-shadow:8px 0 30px rgba(0,0,0,.16);overflow:auto}.koja-ai-panel-head{display:flex;align-items:center;gap:8px;margin-bottom:14px}.koja-ai-panel-head strong{margin-right:auto}.koja-ai-chatlink{display:block;padding:11px 12px;border-radius:11px;text-decoration:none;color:inherit;margin:3px 0}.koja-ai-chatlink.active{background:rgba(127,127,127,.16)}
@media(max-width:700px){.koja-ai-main{padding:10px 12px 20px}.koja-ai-bubble{max-width:88%}.koja-ai-empty h2{font-size:25px}.koja-ai-top{padding-left:10px}}
</style>
<div class="koja-ai-page">
  <div class="koja-ai-top">
    <button class="koja-ai-icon" type="button" aria-label="Recent chats" title="Recent chats" onclick="document.getElementById('kojaRecentChats').classList.add('open')">☰</button>
    <div class="koja-ai-title">🧠 KOJA AI</div>
    <form method="post" style="margin:0"><input type="hidden" name="action" value="new"><button class="koja-ai-icon" type="submit" aria-label="New chat" title="New chat">＋</button></form>
  </div>
  <div class="koja-ai-main">
    <div class="koja-ai-messages">
    {% if messages %}
      {% for item in messages %}<div class="koja-ai-msg {{ 'user' if item.role=='user' else 'assistant' }}"><div class="koja-ai-bubble">{% if item.role!='user' %}<strong>KOJA AI</strong><br>{% endif %}{{ item.content }}</div></div>{% endfor %}
    {% else %}<div class="koja-ai-empty"><h2>How can I help?</h2><p>Ask KOJA AI anything.</p></div>{% endif %}
    </div>
    <div class="koja-ai-compose"><form method="post" enctype="multipart/form-data" id="kojaAiForm"><input type="hidden" name="conversation_id" value="{{ conversation_id }}"><div id="kojaAttachment" class="koja-ai-attachment"><span id="kojaAttachmentIcon">📄</span><span id="kojaAttachmentName"></span><button type="button" onclick="clearKOJAAttachment()" aria-label="Remove attachment">×</button></div><div class="koja-ai-input-row"><div class="koja-ai-tools"><label class="koja-ai-tool" for="kojaAiFile" title="Upload document" aria-label="Upload document">📎</label><input class="koja-ai-file" id="kojaAiFile" type="file" name="attachment" accept=".pdf,.doc,.docx,.txt,.csv,.md,.jpg,.jpeg,.png,.webp"><button class="koja-ai-tool" type="button" id="kojaAiRecord" title="Record voice message" aria-label="Record voice message">🎙️</button></div><textarea name="prompt" id="kojaAiPrompt" maxlength="12000" required placeholder="Message KOJA AI…" rows="1"></textarea><button class="koja-ai-send" type="submit" aria-label="Send" title="Send">↑</button></div></form><p class="small" style="text-align:center;margin:8px 0 0">📎 Add a document or 🎙️ record a voice note. For academic research with source citations, use <a href="{{ url_for('research') }}">KOJA Research</a>.</p></div><script>(function(){const ta=document.getElementById('kojaAiPrompt'),file=document.getElementById('kojaAiFile'),chip=document.getElementById('kojaAttachment'),name=document.getElementById('kojaAttachmentName'),icon=document.getElementById('kojaAttachmentIcon'),recBtn=document.getElementById('kojaAiRecord');function resize(){ta.style.height='auto';ta.style.height=Math.min(ta.scrollHeight,180)+'px'}ta.addEventListener('input',resize);file.addEventListener('change',function(){const f=file.files[0];if(!f)return;name.textContent=f.name;icon.textContent=f.type.startsWith('image/')?'🖼️':(f.type.startsWith('audio/')?'🎵':'📄');chip.classList.add('show');});window.clearKOJAAttachment=function(){file.value='';chip.classList.remove('show');name.textContent=''};let recorder,parts=[],stream;recBtn.addEventListener('click',async function(){if(recorder&&recorder.state==='recording'){recorder.stop();return}try{stream=await navigator.mediaDevices.getUserMedia({audio:true});recorder=new MediaRecorder(stream);parts=[];recorder.ondataavailable=e=>{if(e.data.size)parts.push(e.data)};recorder.onstop=()=>{const blob=new Blob(parts,{type:'audio/webm'});const f=new File([blob],'KOJA-voice-note.webm',{type:'audio/webm'});try{const dt=new DataTransfer();dt.items.add(f);file.files=dt.files;name.textContent=f.name;icon.textContent='🎙️';chip.classList.add('show');ta.value=(ta.value?ta.value+'\n':'')+'[Voice note attached — please process this attachment]';resize()}catch(e){ta.value=(ta.value?ta.value+'\n':'')+'[Voice note recorded]';resize()}stream.getTracks().forEach(t=>t.stop());recBtn.classList.remove('recording');recBtn.textContent='🎙️';};recorder.start();recBtn.classList.add('recording');recBtn.textContent='⏹️';setTimeout(()=>{if(recorder&&recorder.state==='recording')recorder.stop()},60000)}catch(e){alert('Microphone permission is required to record a voice message.')}});resize()})();</script>
  </div>
</div>
<div id="kojaRecentChats" class="koja-ai-drawer"><div class="koja-ai-backdrop" onclick="document.getElementById('kojaRecentChats').classList.remove('open')"></div><aside class="koja-ai-panel"><div class="koja-ai-panel-head"><strong>Recent chats</strong><button class="koja-ai-icon" type="button" onclick="document.getElementById('kojaRecentChats').classList.remove('open')" aria-label="Close">×</button></div>{% for c in conversations %}<a class="koja-ai-chatlink {{ 'active' if c.id|string==conversation_id else '' }}" href="{{ url_for('ai_assistant', conversation_id=c.id) }}">{{ c.title }}</a>{% else %}<p class="small">No saved conversations yet.</p>{% endfor %}</aside></div>
''', conversations=conversations, messages=messages, conversation_id=conversation_id)

@app.route("/documents", methods=["GET", "POST"])
@login_required
def documents():
    """KOJA document library. Uses existing documents table when available and degrades gracefully on older schemas."""
    user = current_user()
    if request.method == "POST":
        title = clean(request.form.get("title"))
        description = clean(request.form.get("description"))
        category = clean(request.form.get("category")) or "Research"
        file = request.files.get("file")
        if not title:
            flash("Enter a document title.", "danger")
            return redirect(url_for("documents"))
        if not file or not file.filename:
            flash("Choose a document file.", "danger")
            return redirect(url_for("documents"))
        uploaded, error = upload_storage(file, "documents", public=False)
        if error:
            flash("Document upload failed: " + str(error)[:500], "danger")
            return redirect(url_for("documents"))
        # Use the known KOJA documents schema instead of sending speculative
        # columns that caused repeated Supabase schema-cache failures.
        payload = {
            "id": str(uuid.uuid4()), "title": title, "description": description,
            "category": category, "user_id": user.get("id"),
            "file_name": uploaded["file_name"], "file_path": uploaded["path"],
            "file_url": uploaded["path"], "approval_status": "pending",
            "is_public": False, "is_active": True, "created_at": utc_now(),
            "updated_at": utc_now()
        }
        row, error = db_insert("documents", payload)
        if error:
            delete_storage_path(uploaded.get("path"))
            flash("Document could not be saved, so the uploaded file was cleaned up. Check the documents table schema.", "danger")
        else:
            flash("Document uploaded and sent for approval.", "success")
            log_activity("document_uploaded", "User uploaded a KOJA document.")
        return redirect(url_for("documents"))
    rows = db_select("documents", order="created_at.desc", limit=200)
    visible = []
    for row in rows:
        owner = row.get("owner_id") or row.get("user_id") or row.get("uploaded_by")
        approved = str(row.get("approval_status") or row.get("status") or "").lower() in ("approved", "published", "active", "public")
        if user.get("is_admin") or str(owner or "") == str(user.get("id") or "") or approved:
            visible.append(row)
    return render_page("Documents", r"""
<div class="hero"><h2>📚 KOJA Documents</h2><p>Upload, find and use research and learning documents. New uploads are sent for administrator approval.</p></div>
<div class="card"><h3>Upload Document</h3><form method="post" enctype="multipart/form-data"><label>Title</label><input name="title" maxlength="220" required><label>Description</label><textarea name="description" maxlength="4000" placeholder="What is this document about?"></textarea><label>Category</label><select name="category"><option>Research</option><option>Academic</option><option>Notes</option><option>Reports</option><option>Books</option><option>Other</option></select><label>File</label><input name="file" type="file" accept=".pdf,.doc,.docx,.txt,.jpg,.jpeg,.png,.webp" required><button class="btn" type="submit">Upload for Approval</button></form></div>
<div class="grid">{% for d in documents %}<div class="card"><h3>{{ d.get('title') or d.get('name') or d.get('filename') or 'KOJA Document' }}</h3><p>{{ d.get('description') or d.get('content') or '' }}</p><p class="small">Category: {{ d.get('category') or 'Research' }} · Status: {{ d.get('approval_status') or d.get('status') or '—' }}</p>{% set did=d.get('id') %}{% if did %}<a class="btn secondary" href="{{ url_for('document_download', document_id=did) }}">Open / Download</a>{% endif %}</div>{% else %}<div class="card"><h3>No documents yet</h3><p>Upload the first KOJA research or learning document.</p></div>{% endfor %}</div>
""", documents=visible)

@app.route("/documents/download/<document_id>")
@login_required
def document_download(document_id):
    user=current_user() or {}
    doc=first_row("documents", {"id": document_id})
    if not doc:
        abort(404)
    owner=str(doc.get("user_id") or doc.get("owner_id") or "")
    approved=str(doc.get("approval_status") or "").lower() in ("approved","published","public","active")
    if not user.get("is_admin") and owner != str(user.get("id") or "") and not approved:
        abort(403)
    storage_path=clean(doc.get("file_path") or doc.get("file_url"))
    public_prefix=f"{SUPABASE_URL.rstrip('/')}/storage/v1/object/public/" if SUPABASE_URL else ""
    if public_prefix and storage_path.startswith(public_prefix):
        rem=storage_path[len(public_prefix):]; bp=f"{STORAGE_BUCKET}/"
        if rem.startswith(bp): storage_path=unquote(rem[len(bp):])
    if storage_path.startswith(f"{STORAGE_BUCKET}/"):
        storage_path=storage_path[len(STORAGE_BUCKET)+1:]
    if not storage_path or not supabase_configured(): abort(404)
    try:
        r=requests.get(sb_storage_url(storage_path),headers=sb_headers(),timeout=30)
        if not r.ok: abort(404)
        filename=secure_filename(doc.get("file_name") or "koja-document") or "koja-document"
        response=send_file(io.BytesIO(r.content),download_name=filename,mimetype=r.headers.get("Content-Type") or "application/octet-stream",max_age=0)
        response.headers["Cache-Control"]="private, no-store"
        return response
    except Exception:
        logger.exception("Document download failed")
        abort(404)

@app.route("/services")
@login_required
def services():
    return render_page("Services", r"""
<div class="hero"><h2>KOJA Services</h2><p>Choose a service.</p></div>
<div class="grid">
<div class="card"><h3>🧠 KOJA AI</h3><a class="btn" href="{{ url_for('ai_assistant') }}">Open AI</a></div>
 <div class="card"><h3>📚 Documents</h3><a class="btn" href="{{ url_for('documents') }}">Open Documents</a></div>
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
            uploaded,error=upload_storage(file,"assignments",public=False)
            if error:
                flash(f"Upload failed: {error}","danger")
                return redirect(url_for("assignments"))

        payload={
            "id":str(uuid.uuid4()),
            "student_id":user["id"],
            "user_id":user["id"],
            "owner_id":user["id"],
            "sender_id":user["id"],
            "tracking_code":make_assignment_tracking_code(),
            "title":title,"description":description,
            "status":"submitted","created_at":utc_now()
        }
        if uploaded:
            payload.update({
                "file_name":uploaded["file_name"],
                "file_path":uploaded["path"],
                "file_url":uploaded["path"],
                "file_size":uploaded["file_size"],
                "mime_type":uploaded["mime_type"]
            })
        row,error=db_insert("assignments",payload)
        if error:
            if uploaded:
                delete_storage_path(uploaded.get("path"))
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
<label>Image / media (optional)</label><input type="file" name="media" accept="image/jpeg,image/png,image/webp,video/mp4,video/webm,video/quicktime">
<button class="btn" type="submit">🌐 Publish Publicly</button></form>
<p class="small">Your post is public and may be visible to people who are not logged in.</p></div>
{% else %}<div class="card"><strong>Want to publish?</strong> <a class="btn" href="{{ url_for('login', next='/public') }}">Login</a> <a class="btn secondary" href="{{ url_for('register', next='/public') }}">Create account</a></div>{% endif %}
<div class="card"><h2>📰 News & Updates</h2><p class="small">Public feed · newest first</p></div>
{% for p in posts %}<article class="card" id="post-{{ p.id }}"><strong>👤 {{ p.author_name }}</strong><div class="small">{{ p.post_type|title }} · {{ p.created_at }}</div>
{% if p.title %}<h2 style="margin-top:10px">{{ p.title }}</h2>{% endif %}<p style="white-space:pre-wrap;line-height:1.7">{{ p.body }}</p>
{% if p.media_url and p.media_type=='video' %}<video controls playsinline preload="metadata" style="width:100%;max-height:620px;border-radius:12px;margin-top:8px;background:#000"><source src="{{ url_for('public_feed_media', post_id=p.id) }}"></video>{% elif p.media_url %}<img src="{{ url_for('public_feed_media', post_id=p.id) }}" alt="Public KOJA post image" loading="lazy" style="width:100%;max-height:620px;object-fit:contain;border-radius:12px;margin-top:8px">{% endif %}
<div class="actions" style="margin-top:12px">{% if user %}<form method="post" action="{{ url_for('public_toggle_like', post_id=p.id) }}" style="display:inline"><button class="btn secondary" type="submit">{{ '❤️ Liked' if p.liked else '🤍 Like' }} · {{ p.like_count }}</button></form>{% else %}<a class="btn secondary" href="{{ url_for('login', next='/public') }}">🤍 Like · {{ p.like_count }}</a>{% endif %}<span class="btn secondary" style="cursor:default">💬 {{ p.comments|length }} Comments</span></div>
{% for c in p.comments %}<div style="padding:9px 0;border-top:1px solid var(--border);margin-top:9px"><strong>{{ c.author_name }}</strong><div>{{ c.body }}</div><div class="small">{{ c.created_at }}</div></div>{% endfor %}
{% if user %}<form method="post" action="{{ url_for('public_comment', post_id=p.id) }}"><input name="body" maxlength="1000" placeholder="Write a comment..." required><button class="btn" type="submit">Comment</button></form>{% else %}<p class="small"><a href="{{ url_for('login', next='/public') }}">Login</a> to comment.</p>{% endif %}
</article>{% else %}<div class="card"><h3>No public updates yet.</h3><p>Be the first KOJA user to share a public update or news.</p></div>{% endfor %}
''', posts=enriched)

@app.route('/public/media/<post_id>')
def public_feed_media(post_id):
    post = first_row('koja_public_posts', {'id': post_id})
    if not post or not as_bool(post.get('is_published')):
        return '', 404
    value = clean(post.get('media_url'))
    if not value:
        return '', 404
    # V40.5 stores a private Storage path. Accept the old public URL format
    # only when it points to this exact Supabase project and bucket.
    path = value
    public_prefix = f"{SUPABASE_URL.rstrip('/')}/storage/v1/object/public/{quote(STORAGE_BUCKET, safe='')}/" if SUPABASE_URL else ''
    if public_prefix and value.startswith(public_prefix):
        path = unquote(value[len(public_prefix):])
    if path.startswith('http://') or path.startswith('https://'):
        return '', 404
    try:
        r = requests.get(sb_storage_url(path), headers=sb_headers(), timeout=20)
        if not r.ok:
            return '', 404
        mime = r.headers.get('Content-Type') or 'application/octet-stream'
        response = send_file(io.BytesIO(r.content), mimetype=mime, download_name='koja-public-media')
        response.headers['Cache-Control'] = 'public, max-age=300'
        return response
    except Exception:
        logger.exception('Public feed media read failed')
        return '', 404

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
        if ext not in {'jpg','jpeg','png','webp','mp4','webm','mov'}:
            flash('Public media must be JPG, PNG, WebP, MP4, WebM or MOV.','danger'); return redirect(url_for('public_feed'))
        uploaded,err=upload_storage(media,'public-feed',public=False)
        if err: flash(f'Media upload failed: {err}','danger'); return redirect(url_for('public_feed'))
    media_type = 'video' if media and media.filename and media.filename.lower().rsplit('.',1)[-1] in {'mp4','webm','mov'} else ('image' if uploaded else None)
    payload={'author_id':current_user().get('id'),'post_type':post_type,'title':title or None,'body':body,
             'media_url':(uploaded or {}).get('path'),'media_type':media_type,'is_published':True}
    _,err=db_insert('koja_public_posts',payload)
    if err and uploaded:
        delete_storage_path(uploaded.get('path'))
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

def delete_storage_path(storage_path):
    """Best-effort cleanup of an uploaded object when its database write fails."""
    storage_path=clean(storage_path).lstrip('/')
    if not storage_path or not supabase_configured():
        return False
    try:
        r=requests.delete(sb_storage_url(storage_path),headers=sb_headers(),timeout=20)
        return bool(r.ok)
    except Exception:
        logger.exception('Storage cleanup failed for %s', storage_path)
        return False

@app.route('/marketplace/post-media/<post_id>')
def marketplace_post_media(post_id):
    post=first_row('koja_marketplace_posts', {'id':post_id})
    if not post or not as_bool(post.get('is_published')) or not post.get('media_url'): abort(404)
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
            if not product or (not as_bool(product.get('is_published')) and str(product.get('seller_id'))!=str((current_user() or {}).get('id'))):
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
            uploaded,err=upload_storage(media,folder,public=False)
            if err:
                flash(f'Media upload failed: {err}','danger')
                return redirect(url_for('marketplace_post_create'))
            media_url=(uploaded or {}).get('path')
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
        if err and media_url:
            delete_storage_path(media_url)
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
    if not product or not as_bool(product.get('is_published')): abort(404)
    seller=marketplace_seller_name(product.get('seller_id')); uid=(current_user() or {}).get('id') if current_user() else None
    return render_page(product.get('title') or 'Digital Product',r'''
<div class="card"><div class="small">{{ product.category }} · Seller: {{ seller }}</div><h1>{{ product.title }}</h1>{% if product.cover_url %}<img src="{{ url_for('marketplace_cover', product_id=product.id) }}" alt="{{ product.title }}" style="display:block;width:100%;max-height:520px;object-fit:contain;border-radius:12px;background:var(--bg)">{% endif %}<p style="white-space:pre-wrap;line-height:1.75">{{ product.description }}</p><h2>{{ 'FREE' if product.price|float<=0 else money(product.price, product.currency) }}</h2>{% if user %}{% if access %}<a class="btn success" href="{{ url_for('marketplace_download', product_id=product.id) }}">⬇️ Download / Access</a>{% elif product.price|float<=0 %}<form method="post" action="{{ url_for('marketplace_buy', product_id=product.id) }}"><button class="btn success" type="submit">🎁 Get Free Product</button></form>{% else %}<form method="post" action="{{ url_for('marketplace_buy', product_id=product.id) }}"><label>Mobile-money network</label><select name="network" required><option value="">Select network</option><option value="MTN">MTN</option><option value="AIRTEL">Airtel</option><option value="ZAMTEL">Zamtel</option></select><label>Mobile-money phone</label><input name="phone" value="{{ user.phone or '' }}" required inputmode="tel"><button class="btn" type="submit">🛒 Request Purchase · {{ money(product.price, product.currency) }}</button></form><p class="small">Secure checkout is handled by Flutterwave when FLW_SECRET_KEY is configured. KOJA verifies the transaction on the server before releasing the digital file.</p>{% endif %}{% else %}<a class="btn" href="{{ url_for('login', next=request.path) }}">Login to Purchase / Download</a>{% endif %}</div>
''',product=product,seller=seller,access=marketplace_has_access(product,uid),money=marketplace_money)

@app.route('/marketplace/buy/<product_id>',methods=['POST'])
@login_required
def marketplace_buy(product_id):
    product=marketplace_product(product_id); user=current_user() or {}; uid=user.get('id')
    if not product or not as_bool(product.get('is_published')): abort(404)
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
    network=clean(request.form.get('network')).upper()
    phone=clean(request.form.get('phone')) or clean(user.get('phone'))
    if network not in ('MTN','AIRTEL','ZAMTEL') or not phone:
        flash('Select your Zambian mobile-money network and enter the mobile-money phone number.','warning')
        return redirect(url_for('marketplace_product_view',product_id=product_id))
    payload={'tx_ref':tx_ref,'amount':int(round(amount)),'currency':(product.get('currency') or 'ZMW').upper(),'email':email,'fullname':first_nonempty(user.get('name'),user.get('full_name'),email),'phone_number':phone,'network':network,'order_id':str(order.get('id') or ''),'redirect_url':url_for('marketplace_payment_callback',_external=True,tx_ref=tx_ref),'meta':{'koja_order_id':str(order.get('id') or ''),'koja_product_id':str(product_id)}}
    try:
        r=requests.post(FLW_BASE_URL+'/charges?type=mobile_money_zambia',headers={'Authorization':'Bearer '+FLW_SECRET_KEY,'Content-Type':'application/json','Accept':'application/json'},json=payload,timeout=30)
        data=json_or_empty(r)
        authorization=((data.get('meta') or {}).get('authorization') or {}) if isinstance(data,dict) else {}
        redirect_url=authorization.get('redirect')
        if r.ok and str(data.get('status') or '').lower()=='success' and redirect_url:
            return redirect(redirect_url)
        logger.error('Flutterwave V3 Zambia checkout creation failed: %s %s',r.status_code,str(data)[:1500])
    except Exception as exc:
        logger.exception('Flutterwave checkout error: %s',exc)
    flash('Payment checkout could not be started. Please try again.','danger')
    return redirect(url_for('marketplace_product_view',product_id=product_id))

def _flutterwave_verify(transaction_id=None, tx_ref=None):
    """Verify a Flutterwave V3 transaction, with a tx_ref lookup fallback.

    Flutterwave's Zambia test flow can briefly expose the transaction through the
    callback/webhook before the direct verify response is populated. We therefore
    retry the ID endpoint and, if it still has no data, query the V3 transactions
    collection by tx_ref. Value is released only from a verified successful record.
    """
    if not FLW_SECRET_KEY:
        logger.error('Flutterwave verification skipped: FLW_SECRET_KEY is not configured')
        return None
    headers={'Authorization':'Bearer '+FLW_SECRET_KEY,'Content-Type':'application/json','Accept':'application/json'}

    def _extract(body):
        if not isinstance(body,dict):
            return None
        data=body.get('data')
        if isinstance(data,dict) and data:
            return data
        if isinstance(data,list):
            for item in data:
                if isinstance(item,dict) and item:
                    return item
        return None

    try:
        if transaction_id:
            for attempt in range(3):
                url=FLW_BASE_URL+'/transactions/'+quote(str(transaction_id), safe='')+'/verify'
                r=requests.get(url,headers=headers,timeout=30)
                raw=r.text or ''
                body=json_or_empty(r)
                tx=_extract(body)
                if tx:
                    logger.info('Flutterwave verified transaction id=%s status=%s tx_ref=%s amount=%s currency=%s',transaction_id,tx.get('status'),tx.get('tx_ref') or tx.get('txRef') or tx.get('reference'),tx.get('amount'),tx.get('currency'))
                    return tx
                logger.error('Flutterwave verification attempt=%s HTTP=%s content_type=%s body=%s',attempt+1,r.status_code,r.headers.get('Content-Type',''),raw[:1200])
                if attempt < 2:
                    time.sleep(2 if attempt == 0 else 4)

        if tx_ref:
            # V3 transaction collection supports querying by merchant tx_ref.
            from datetime import datetime, timezone, timedelta
            now=datetime.now(timezone.utc)
            params={
                'from':(now-timedelta(days=2)).strftime('%Y-%m-%d'),
                'to':(now+timedelta(days=1)).strftime('%Y-%m-%d'),
                'page':1,
                'tx_ref':str(tx_ref),
            }
            r=requests.get(FLW_BASE_URL+'/transactions',headers=headers,params=params,timeout=30)
            raw=r.text or ''
            body=json_or_empty(r)
            tx=_extract(body)
            if tx:
                logger.info('Flutterwave verified transaction by tx_ref=%s id=%s status=%s',tx_ref,tx.get('id'),tx.get('status'))
                return tx
            logger.error('Flutterwave tx_ref lookup failed HTTP=%s content_type=%s body=%s',r.status_code,r.headers.get('Content-Type',''),raw[:1200])
    except Exception:
        logger.exception('Flutterwave transaction verification error')
    return None

def _flutterwave_payment_valid(tx, tx_ref, expected_amount, expected_currency):
    try:
        paid=float(tx.get('amount') or 0)
        expected=float(expected_amount or 0)
    except Exception:
        return False
    return bool(
        tx and str(tx.get('status') or '').lower() == 'successful'
        and str(tx.get('tx_ref') or tx.get('txRef') or tx.get('reference') or '') == str(tx_ref)
        and str(tx.get('currency') or '').upper() == str(expected_currency or 'ZMW').upper()
        and paid >= expected
    )

def _finalize_marketplace_order(order, tx):
    if not order or not tx: return False
    tx_ref=str(order.get('payment_reference') or '')
    if not _flutterwave_payment_valid(tx, tx_ref, order.get('amount'), order.get('currency')): return False
    if str(order.get('status') or '').lower() == 'paid': return True
    updated,err=db_update('koja_marketplace_orders',{'id':order.get('id'),'status':'pending'},
        {'status':'paid','payment_method':'flutterwave','payment_transaction_id':str(tx.get('id') or ''),'updated_at':utc_now()})
    if updated:
        return True
    current=first_row('koja_marketplace_orders',{'id':order.get('id')})
    if str((current or {}).get('status') or '').lower()=='paid':
        return True
    if err:
        logger.error('KOJA Digital order finalization DB error order=%s: %s',order.get('id'),err)
    return False

def _finalize_market_order(order, tx):
    if not order or not tx: return False
    tx_ref=str(order.get('payment_reference') or '')
    if not _flutterwave_payment_valid(tx, tx_ref, order.get('total_amount'), order.get('currency')): return False
    if str(order.get('status') or '').lower() in {'paid','completed'}: return True
    # Atomic state transition prevents webhook/callback double-finalization.
    updated,err=db_update('koja_market_orders',{'id':order.get('id'),'status':'pending'},
        {'status':'paid','payment_method':'flutterwave','payment_transaction_id':str(tx.get('id') or ''),'payout_status':'pending','updated_at':utc_now()})
    if not updated:
        current=first_row('koja_market_orders',{'id':order.get('id')})
        if str((current or {}).get('status') or '').lower() in {'paid','completed'}:
            return True
        if err:
            logger.error('KOJA Market order finalization DB error order=%s: %s',order.get('id'),err)
        return False
    p=market_product(order.get('product_id'))
    if p and str(p.get('product_type') or 'physical')=='physical':
        try:
            qty=max(1,int(order.get('quantity') or 1)); stock=max(0,int(p.get('stock') or 0)-qty)
            db_update('koja_market_products',{'id':p.get('id')},{'stock':stock,'updated_at':utc_now()})
        except Exception: logger.exception('KOJA Market stock finalization error')
    buyer_id=order.get('buyer_id')
    gross=_money_num(order.get('total_amount')); commission=_money_num(order.get('commission_amount')); platform_fee=_money_num(order.get('platform_fee')); net=max(0,gross-commission-platform_fee)
    # Ledger/payment-fee/delivery inserts are performed once after the atomic paid transition.
    db_insert('koja_market_ledger',{'order_id':order.get('id'),'seller_id':order.get('seller_id'),'buyer_id':buyer_id,'gross_amount':gross,'commission_amount':commission,'platform_fee':platform_fee,'net_amount':net,'currency':order.get('currency') or 'ZMW','status':'pending','created_at':utc_now()})
    db_insert('koja_market_payment_fees',{'order_id':order.get('id'),'buyer_id':buyer_id,'amount':platform_fee,'currency':order.get('currency') or 'ZMW','fee_type':'platform_service_fee','provider':'flutterwave','reference':tx_ref,'status':'captured','created_at':utc_now()})
    if p and str(p.get('product_type') or 'physical')=='physical':
        db_insert('koja_market_delivery_jobs',{'order_id':order.get('id'),'customer_id':buyer_id,'delivery_address':order.get('delivery_address'),'delivery_fee':_money_num(order.get('delivery_fee')),'status':'requested','tracking_code':'KMD-'+secrets.token_hex(5).upper(),'created_at':utc_now(),'updated_at':utc_now()})
    _sync_market_order_to_business(dict(order,status='paid'))
    return True

@app.route('/marketplace/payment/callback')
@login_required
def marketplace_payment_callback():
    tx_ref=clean(request.args.get('tx_ref') or request.args.get('reference'))
    transaction_id=clean(request.args.get('transaction_id') or request.args.get('id'))
    # Flutterwave V3 may return the full transaction response in `resp`, with camelCase fields.
    resp_raw=clean(request.args.get('resp'))
    if resp_raw:
        try:
            resp_obj=json.loads(resp_raw)
            resp_data=(resp_obj.get('data') or {}) if isinstance(resp_obj,dict) else {}
            tx_ref=tx_ref or clean(resp_data.get('tx_ref') or resp_data.get('txRef') or resp_data.get('reference'))
            transaction_id=transaction_id or clean(resp_data.get('id') or resp_data.get('transaction_id'))
        except Exception:
            logger.warning('Flutterwave callback resp could not be parsed')
    uid=(current_user() or {}).get('id')
    tx=None
    # Verify the transaction server-side and recover tx_ref from the verified record when needed.
    if transaction_id:
        tx=_flutterwave_verify(transaction_id, tx_ref)
        if tx and not tx_ref:
            tx_ref=clean(tx.get('tx_ref') or tx.get('txRef') or tx.get('reference'))
    if not tx_ref:
        flash('Payment reference was missing. Please return to KOJA and check My Orders; the payment will be confirmed from the Flutterwave webhook if it completed.','warning')
        return redirect(url_for('marketplace_my'))
    order=first_row('koja_marketplace_orders',{'payment_reference':tx_ref,'buyer_id':uid})
    if not order:
        flash('Marketplace payment order could not be found.','danger'); return redirect(url_for('marketplace_my'))
    if str(order.get('status') or '').lower()=='paid':
        return redirect(url_for('marketplace_download',product_id=order.get('product_id')))
    if tx is None and transaction_id:
        tx=_flutterwave_verify(transaction_id, tx_ref)
    if tx and _finalize_marketplace_order(order,tx):
        flash('Payment verified successfully. Your digital product is now available.','success')
        return redirect(url_for('marketplace_download',product_id=order.get('product_id')))
    flash('Payment is still pending. KOJA will confirm it automatically when Flutterwave reports the successful transaction.','info')
    return redirect(url_for('marketplace_my'))

@app.route('/marketplace/cover/<product_id>')
def marketplace_cover(product_id):
    product=marketplace_product(product_id)
    if not product or not product.get('cover_url'): abort(404)
    if not as_bool(product.get('is_published')):
        user=current_user() or {}
        if str(product.get('seller_id') or '') != str(user.get('id') or '') and not user.get('is_admin'):
            abort(404)
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
    if not product or not as_bool(product.get('is_published')) or not marketplace_has_access(product,uid): abort(404)
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
        response=send_file(io.BytesIO(r.content),download_name=filename,mimetype=r.headers.get('Content-Type') or 'application/octet-stream',as_attachment=True,max_age=0)
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Content-Security-Policy']='sandbox'
        response.headers['Cache-Control']='private, no-store'
        return response
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
        uploaded,err=upload_storage(digital,'marketplace/products', public=False)
        if err: flash(f'Digital file upload failed: {err}','danger'); return redirect(url_for('marketplace_sell'))
        cover_url=None
        if cover and cover.filename:
            cext=cover.filename.lower().rsplit('.',1)[-1] if '.' in cover.filename else ''
            if cext in {'jpg','jpeg','png','webp'}:
                cu,cerr=upload_storage(cover,'marketplace/covers', public=False)
                if not cerr: cover_url=(cu or {}).get('path')
        payload={'seller_id':(current_user() or {}).get('id'),'title':title,'description':description,'category':category,'price':price,'currency':'ZMW','cover_url':cover_url,'file_url':(uploaded or {}).get('path'),'file_name':digital.filename,'file_size':getattr(digital,'content_length',None),'is_published':False}
        _,err=db_insert('koja_marketplace_products',payload)
        if err:
            delete_storage_path((uploaded or {}).get('path'))
            if cover_url: delete_storage_path(cover_url)
        flash('Product submitted. It is hidden until published/approved.' if not err else 'Product could not be saved. Run MARKETPLACE.sql in Supabase first.','success' if not err else 'danger')
        return redirect(url_for('marketplace_my'))
    return render_page('Sell Digital Product',r'''<div class="hero"><h1>💼 Sell a Digital Product</h1><p>Upload a digital file and create a marketplace listing. New listings are unpublished until approved.</p></div><div class="card"><form method="post" enctype="multipart/form-data"><label>Product title</label><input name="title" maxlength="180" required placeholder="e.g. Grade 12 Mathematics Revision Guide"><label>Description</label><textarea name="description" maxlength="10000" required placeholder="Explain what the buyer receives..."></textarea><div class="grid"><div><label>Category</label><select name="category">{% for c in categories %}<option>{{ c }}</option>{% endfor %}</select></div><div><label>Price (ZMW)</label><input name="price" type="number" min="0" step="0.01" value="0" required></div></div><label>Digital product file</label><input type="file" name="digital_file" required><label>Cover image (optional)</label><input type="file" name="cover" accept="image/jpeg,image/png,image/webp"><button class="btn" type="submit">📤 Submit Product</button></form><p class="small">Maximum upload size follows KOJA's 15 MB server limit.</p></div>''',categories=MARKETPLACE_CATEGORIES)

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
    return render_page('My Marketplace',r'''<div class="hero"><h1>📦 My Marketplace</h1><div class="actions"><a class="btn" href="{{ url_for('marketplace_sell') }}">+ Sell Product</a><a class="btn secondary" href="{{ url_for('marketplace') }}">Browse Marketplace</a></div></div><div class="card"><h2>My Products</h2><table><tr><th>Product</th><th>Price</th><th>Status</th></tr>{% for p in products %}<tr><td>{{ p.title }}</td><td>{{ money(p.price,p.currency) if p.price|float>0 else 'FREE' }}</td><td>{{ 'Published' if p.is_published else 'Pending review' }}</td></tr>{% else %}<tr><td colspan="3">No products yet.</td></tr>{% endfor %}</table></div><div class="card"><h2>Sales / Orders</h2><table><tr><th>Product</th><th>Amount</th><th>Status</th></tr>{% for o in orders %}<tr><td>{{ pm.get(o.product_id,{}).get('title','Digital product') }}</td><td>{{ money(o.amount,o.currency) }}</td><td>{{ o.status }}</td></tr>{% else %}<tr><td colspan="3">No orders yet.</td></tr>{% endfor %}</table></div><div class="card"><h2>My Purchases</h2><table><tr><th>Product</th><th>Amount</th><th>Status</th><th></th></tr>{% for o in purchases %}{% set pp=pm.get(o.product_id) %}<tr><td>{{ pp.title if pp else 'Digital product' }}</td><td>{{ money(o.amount,o.currency) }}</td><td>{{ o.status }}</td><td>{% if pp and o.status=='paid' %}<a class="btn success" href="{{ url_for('marketplace_download',product_id=pp.id) }}">Download</a>{% endif %}</td></tr>{% else %}<tr><td colspan="4">No purchases yet.</td></tr>{% endfor %}</table></div>''',products=products,orders=orders,purchases=purchases,pm=pm,money=marketplace_money)


# ============================================================
# KOJA MARKET — V1 (BUILT ON V52 FOUNDATION) — 2026.09.08-MARKET-V1
# Hybrid African marketplace: physical + digital goods, sellers,
# orders, checkout, commission accounting and delivery handoff.
# Existing KOJA Digital Marketplace and Communications are preserved.
# ============================================================

KOJA_MARKET_SQL = r'''
create table if not exists public.koja_market_products (
 id uuid primary key default gen_random_uuid(),
 seller_id uuid not null,
 title text not null,
 description text not null default '',
 category text not null default 'Other',
 product_type text not null default 'physical',
 price numeric(14,2) not null default 0 check (price >= 0),
 currency text not null default 'ZMW',
 stock integer not null default 1 check (stock >= 0),
 sku text,
 image_url text,
 digital_file_url text,
 digital_file_name text,
 delivery_available boolean not null default true,
 delivery_fee numeric(14,2) not null default 0 check (delivery_fee >= 0),
 location text,
 is_published boolean not null default false,
 approval_status text not null default 'pending',
 created_at timestamptz not null default now(),
 updated_at timestamptz not null default now()
);
create index if not exists koja_market_products_feed_idx on public.koja_market_products(is_published,approval_status,created_at desc);
create index if not exists koja_market_products_seller_idx on public.koja_market_products(seller_id,created_at desc);
create index if not exists koja_market_products_category_idx on public.koja_market_products(category,created_at desc);

create table if not exists public.koja_market_orders (
 id uuid primary key default gen_random_uuid(),
 order_number text unique not null,
 product_id uuid not null references public.koja_market_products(id) on delete restrict,
 buyer_id uuid not null,
 seller_id uuid not null,
 quantity integer not null default 1 check (quantity > 0),
 item_amount numeric(14,2) not null default 0,
 delivery_fee numeric(14,2) not null default 0,
 total_amount numeric(14,2) not null default 0,
 commission_amount numeric(14,2) not null default 0,
 seller_amount numeric(14,2) not null default 0,
 currency text not null default 'ZMW',
 status text not null default 'pending',
 payment_method text,
 payment_reference text,
 payment_transaction_id text,
 recipient_name text,
 recipient_phone text,
 delivery_address text,
 notes text,
 created_at timestamptz not null default now(),
 updated_at timestamptz not null default now()
);
create index if not exists koja_market_orders_buyer_idx on public.koja_market_orders(buyer_id,created_at desc);
create index if not exists koja_market_orders_seller_idx on public.koja_market_orders(seller_id,created_at desc);
create index if not exists koja_market_orders_status_idx on public.koja_market_orders(status,created_at desc);

create table if not exists public.koja_market_sellers (
 id uuid primary key default gen_random_uuid(),
 user_id uuid unique not null,
 store_name text not null,
 description text default '',
 phone text,
 location text,
 approval_status text not null default 'pending',
 is_active boolean not null default true,
 created_at timestamptz not null default now(),
 updated_at timestamptz not null default now()
);
create index if not exists koja_market_sellers_status_idx on public.koja_market_sellers(approval_status,is_active);

-- Safe compatibility additions when the tables already exist.
alter table public.koja_market_products add column if not exists product_type text default 'physical';
alter table public.koja_market_products add column if not exists stock integer default 1;
alter table public.koja_market_products add column if not exists sku text;
alter table public.koja_market_products add column if not exists image_url text;
alter table public.koja_market_products add column if not exists digital_file_url text;
alter table public.koja_market_products add column if not exists digital_file_name text;
alter table public.koja_market_products add column if not exists delivery_available boolean default true;
alter table public.koja_market_products add column if not exists delivery_fee numeric(14,2) default 0;
alter table public.koja_market_products add column if not exists location text;
alter table public.koja_market_products add column if not exists approval_status text default 'pending';
create table if not exists public.koja_market_cart (id uuid primary key default gen_random_uuid(), user_id uuid not null, product_id uuid not null references public.koja_market_products(id) on delete cascade, quantity integer not null default 1 check(quantity>0), created_at timestamptz not null default now(), updated_at timestamptz not null default now(), unique(user_id,product_id));
create table if not exists public.koja_market_wishlist (id uuid primary key default gen_random_uuid(), user_id uuid not null, product_id uuid not null references public.koja_market_products(id) on delete cascade, created_at timestamptz not null default now(), unique(user_id,product_id));
'''

KOJA_MARKET_CATEGORIES = [
    'Electronics','Phones & Accessories','Computers','Clothing & Fashion',
    'Beauty & Personal Care','Home & Furniture','Food & Groceries',
    'Books & Education','Agriculture','Construction & Hardware',
    'Vehicles & Parts','Health & Wellness','Business & Office',
    'Digital Products','Services','Other'
]
KOJA_MARKET_TYPES = {'physical','digital'}
KOJA_MARKET_COMMISSION_RATE = 0.10

def market_product(pid):
    return first_row('koja_market_products', {'id': pid})

def market_seller(uid):
    return first_row('koja_market_sellers', {'user_id': uid})

def market_money(v, currency='ZMW'):
    try: return f'{currency} {float(v or 0):,.2f}'
    except Exception: return f'{currency} 0.00'

def market_order_number():
    return 'KJM-' + datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S') + '-' + uuid.uuid4().hex[:6].upper()

def market_image_path(url):
    u=clean(url); prefix=f"{SUPABASE_URL.rstrip('/')}/storage/v1/object/public/" if SUPABASE_URL else ''
    if prefix and u.startswith(prefix):
        rem=u[len(prefix):]; bp=f'{STORAGE_BUCKET}/'
        if rem.startswith(bp): return unquote(rem[len(bp):])
    u=u.lstrip('/')
    if u.startswith(f'{STORAGE_BUCKET}/'): u=u[len(STORAGE_BUCKET)+1:]
    return u

@app.route('/market')
def koja_market():
    user = current_user()
    q=clean(request.args.get('q')); category=clean(request.args.get('category')); ptype=clean(request.args.get('type'))
    rows=db_select('koja_market_products',order='created_at.desc',limit=300) or []
    products=[]
    for x in rows:
        if not as_bool(x.get('is_published')) or str(x.get('approval_status') or 'pending').lower() not in {'approved','active'}: continue
        if q:
            hay=' '.join(str(x.get(k) or '') for k in ('title','description','category','location','sku')).lower()
            if q.lower() not in hay: continue
        if category and str(x.get('category') or '') != category: continue
        if ptype and str(x.get('product_type') or 'physical') != ptype: continue
        x=dict(x); x['seller_name']=(market_seller(x.get('seller_id')) or {}).get('store_name') or marketplace_seller_name(x.get('seller_id'))
        x['price_display']=market_money(x.get('price'),x.get('currency') or 'ZMW')
        products.append(x)
    cart_count=0
    if user:
        cart_rows=db_select('koja_market_cart',{'user_id':user.get('id')},limit=100) or []
        cart_count=sum(max(0,int(x.get('quantity') or 0)) for x in cart_rows)
    return render_page('KOJA Market',r'''
<div class="hero"><h1>🛍️ KOJA Market</h1><p>Buy and sell products and services across Africa — physical goods, digital products, local sellers and delivery.</p>
<div class="actions">
<a class="btn" href="#products">🛒 Buy / Browse</a>
<a class="btn" href="{{ url_for('market_sell') if user else url_for('login',next='/market/sell') }}">🏪 Sell a Product</a>
{% if user %}<a class="btn secondary" href="{{ url_for('market_cart') }}">🛍️ Cart{% if cart_count %} ({{ cart_count }}){% endif %}</a><a class="btn secondary" href="{{ url_for('market_wishlist') }}">❤️ Wishlist</a><a class="btn secondary" href="{{ url_for('market_my') }}">📦 My Orders / Store</a>{% else %}<a class="btn secondary" href="{{ url_for('login',next='/market/cart') }}">🛍️ Cart</a>{% endif %}
</div></div>
<div class="card"><h2>Seller Center</h2><div class="actions"><a class="btn" href="{{ url_for('market_sell') if user else url_for('login',next='/market/sell') }}">➕ Add Product</a>{% if user %}<a class="btn secondary" href="{{ url_for('market_my') }}">📊 Seller Dashboard</a><a class="btn secondary" href="{{ url_for('market_seller_register') }}">🏬 My Store</a><a class="btn secondary" href="{{ url_for('seller_verification') }}">✓ Verification</a><a class="btn secondary" href="{{ url_for('market_seller_subscription') }}">💎 Subscription</a><a class="btn secondary" href="{{ url_for('market_advertise') }}">📣 Advertising</a><a class="btn secondary" href="{{ url_for('market_earnings') }}">📈 Earnings</a><a class="btn secondary" href="{{ url_for('seller_wallet') }}">💰 Wallet</a><a class="btn secondary" href="{{ url_for('market_seller_payouts') }}">💸 Payouts</a><a class="btn secondary" href="{{ url_for('referrals') }}">🤝 Referrals</a>{% else %}<a class="btn secondary" href="{{ url_for('login',next='/market/seller/register') }}">📝 Become a Seller</a>{% endif %}</div></div>
<div class="card"><form method="get" class="actions"><input name="q" value="{{ q }}" placeholder="Search products, shops, services..."><select name="category"><option value="">All categories</option>{% for c in categories %}<option value="{{ c }}" {% if category==c %}selected{% endif %}>{{ c }}</option>{% endfor %}</select><select name="type"><option value="">All types</option><option value="physical" {% if ptype=='physical' %}selected{% endif %}>Physical</option><option value="digital" {% if ptype=='digital' %}selected{% endif %}>Digital</option></select><button class="btn" type="submit">🔎 Search</button></form></div>
<div id="products" class="grid">{% for p in products %}<div class="card"><h3>{{ p.title }}</h3><p class="small">{{ p.category }} · {{ 'Digital' if p.product_type=='digital' else 'Physical' }} · {{ p.seller_name }}</p>{% if p.image_url %}<img src="{{ url_for('market_image',product_id=p.id) }}" alt="{{ p.title }}" style="width:100%;max-height:240px;object-fit:contain;border-radius:10px">{% endif %}<p>{{ p.description[:220] }}{% if p.description|length>220 %}…{% endif %}</p><h3>{{ p.price_display }}</h3>{% if p.product_type=='physical' %}<p class="small">Stock: {{ p.stock }}{% if p.location %} · {{ p.location }}{% endif %}</p>{% endif %}<div class="actions" style="margin-top:12px"><a class="btn secondary" href="{{ url_for('market_product_view',product_id=p.id) }}">View</a>{% if user and user.id|string != p.seller_id|string and (p.product_type!='physical' or p.stock|int>0) %}<form method="post" action="{{ url_for('market_cart_add',product_id=p.id) }}" style="display:inline"><input type="hidden" name="quantity" value="1"><button class="btn" type="submit">🛒 Add to Cart</button></form><a class="btn" href="{{ url_for('market_product_view',product_id=p.id) }}">⚡ Buy Now</a>{% elif not user %}<a class="btn" href="{{ url_for('login',next=url_for('market_product_view',product_id=p.id)) }}">🔐 Login to Buy</a>{% endif %}</div></div>{% else %}<div class="card"><h3>No products found</h3><p>Try another search or become a seller.</p></div>{% endfor %}</div>
''',products=products,categories=KOJA_MARKET_CATEGORIES,q=q,category=category,ptype=ptype,user=user,cart_count=cart_count)

@app.route('/market/image/<product_id>')
def market_image(product_id):
    p=market_product(product_id)
    if not p or not p.get('image_url') or not as_bool(p.get('is_published')): abort(404)
    path=market_image_path(p.get('image_url'))
    if not path or not supabase_configured(): abort(404)
    try:
        r=requests.get(sb_storage_url(path),headers=sb_headers(),timeout=20)
        if not r.ok: abort(404)
        resp=send_file(io.BytesIO(r.content),mimetype=r.headers.get('Content-Type') or 'image/jpeg',max_age=3600)
        resp.headers['Cache-Control']='public,max-age=3600'; return resp
    except Exception: abort(404)

@app.route('/market/product/<product_id>')
def market_product_view(product_id):
    p=market_product(product_id)
    if not p or not as_bool(p.get('is_published')) or str(p.get('approval_status') or '').lower() not in {'approved','active'}: abort(404)
    seller=market_seller(p.get('seller_id')) or {}; seller_name=seller.get('store_name') or marketplace_seller_name(p.get('seller_id'))
    return render_page('Market Product',r'''
<div class="card"><a href="{{ '/market' }}">← KOJA Market</a>{% if product.image_url %}<img src="{{ url_for('market_image',product_id=product.id) }}" alt="{{ product.title }}" style="display:block;width:100%;max-height:500px;object-fit:contain;margin:14px 0;border-radius:12px">{% endif %}<p class="small">{{ product.category }} · {{ 'Digital product' if product.product_type=='digital' else 'Physical product' }}</p><h1>{{ product.title }}</h1><p style="white-space:pre-wrap;line-height:1.75">{{ product.description }}</p><h2>{{ money(product.price,product.currency) }}</h2><p class="small">Seller: {{ seller_name }}{% if product.location %} · {{ product.location }}{% endif %}</p>{% if product.product_type=='physical' %}<p><strong>Stock:</strong> {{ product.stock }}</p>{% endif %}{% if user and user.id|string != product.seller_id|string and (product.product_type!='physical' or product.stock|int>0) %}<form method="post" action="{{ url_for('market_cart_add',product_id=product.id) }}" class="actions"><label style="width:100%">Quantity<input name="quantity" type="number" min="1" max="{{ product.stock if product.product_type=='physical' else 1 }}" value="1" required></label><button class="btn secondary" type="submit">🛒 Add to Cart</button></form><form method="post" action="{{ url_for('market_order_create',product_id=product.id) }}"><label>Mobile-money network</label><select name="network" required><option value="">Select network</option><option value="MTN">MTN</option><option value="AIRTEL">Airtel</option><option value="ZAMTEL">Zamtel</option></select><label>Mobile-money phone</label><input name="phone" value="{{ user.phone or '' }}" required inputmode="tel"><label>Quantity</label><input name="quantity" type="number" min="1" max="{{ product.stock if product.product_type=='physical' else 1 }}" value="1" required>{% if product.product_type=='physical' %}<label>Recipient name</label><input name="recipient_name" required><label>Phone</label><input name="recipient_phone" required><label>Delivery address</label><textarea name="delivery_address" required placeholder="Town, area, house/shop details"></textarea><label>Notes (optional)</label><textarea name="notes"></textarea>{% endif %}<button class="btn" type="submit">⚡ Buy Now</button></form>{% elif not user %}<a class="btn" href="{{ url_for('login',next=request.path) }}">Login to Buy</a>{% else %}<p class="small">This is your listing.</p>{% endif %}</div>
''',product=p,seller_name=seller_name,money=market_money)

@app.route('/market/order/<product_id>',methods=['POST'])
@login_required
def market_order_create(product_id):
    p=market_product(product_id); user=current_user() or {}; uid=user.get('id')
    if not p or not as_bool(p.get('is_published')) or str(p.get('approval_status') or '').lower() not in {'approved','active'}: abort(404)
    if str(p.get('seller_id'))==str(uid): flash('You cannot purchase your own listing.','warning'); return redirect(url_for('market_product_view',product_id=product_id))
    try: qty=max(1,int(request.form.get('quantity') or 1))
    except Exception: qty=1
    if str(p.get('product_type') or 'physical')=='physical' and qty>int(p.get('stock') or 0): flash('Not enough stock available.','danger'); return redirect(url_for('market_product_view',product_id=product_id))
    price=float(p.get('price') or 0); delivery=float(p.get('delivery_fee') or 0) if str(p.get('product_type'))=='physical' else 0
    item=price*qty; total=item+delivery; commission=round(total*KOJA_MARKET_COMMISSION_RATE,2); seller_amount=round(total-commission,2)
    payload={'order_number':market_order_number(),'product_id':product_id,'buyer_id':uid,'seller_id':p.get('seller_id'),'quantity':qty,'item_amount':item,'delivery_fee':delivery,'total_amount':total,'commission_amount':commission,'seller_amount':seller_amount,'currency':p.get('currency') or 'ZMW','status':'pending','recipient_name':clean(request.form.get('recipient_name')) or user.get('name') or user.get('full_name'),'recipient_phone':clean(request.form.get('recipient_phone')) or user.get('phone'),'delivery_address':clean(request.form.get('delivery_address')),'notes':clean(request.form.get('notes')),'created_at':utc_now(),'updated_at':utc_now()}
    order,err=db_insert('koja_market_orders',payload)
    if err: flash('Order could not be created. Run KOJA_MARKET.sql in Supabase.','danger'); return redirect(url_for('market_product_view',product_id=product_id))
    if total<=0:
        db_update('koja_market_orders',{'id':order.get('id')},{'status':'paid','updated_at':utc_now()});
        return redirect(url_for('market_my'))
    if not FLW_SECRET_KEY:
        flash('Order created, but online payment is not configured. Add FLW_SECRET_KEY to Render Environment Variables.','warning'); return redirect(url_for('market_my'))
    tx_ref='KOJA-MARKET-'+str(order.get('order_number'))
    db_update('koja_market_orders',{'id':order.get('id')},{'payment_reference':tx_ref,'updated_at':utc_now()})
    email=user.get('email') or ''
    network=clean(request.form.get('network')).upper()
    phone=clean(request.form.get('phone')) or clean(request.form.get('recipient_phone')) or clean(user.get('phone'))
    if network not in ('MTN','AIRTEL','ZAMTEL') or not phone:
        flash('Select your Zambian mobile-money network and enter the mobile-money phone number.','warning')
        return redirect(url_for('market_product_view',product_id=product_id))
    payload_fw={'tx_ref':tx_ref,'amount':int(round(total)),'currency':(p.get('currency') or 'ZMW').upper(),'email':email,'fullname':first_nonempty(user.get('name'),user.get('full_name'),email),'phone_number':phone,'network':network,'order_id':str(order.get('id') or ''),'redirect_url':url_for('market_payment_callback',_external=True,tx_ref=tx_ref),'meta':{'koja_order_id':str(order.get('id') or ''),'koja_product_id':str(product_id)}}
    try:
        r=requests.post(FLW_BASE_URL+'/charges?type=mobile_money_zambia',headers={'Authorization':'Bearer '+FLW_SECRET_KEY,'Content-Type':'application/json','Accept':'application/json'},json=payload_fw,timeout=30); body=json_or_empty(r)
        authorization=((body.get('meta') or {}).get('authorization') or {}) if isinstance(body,dict) else {}
        redirect_url=authorization.get('redirect')
        if r.ok and str(body.get('status') or '').lower()=='success' and redirect_url:
            return redirect(redirect_url)
        logger.error('KOJA Market V3 Zambia checkout failed: %s %s',r.status_code,str(body)[:1500])
    except Exception: logger.exception('KOJA Market checkout error')
    flash('Order was created, but checkout could not be started.','danger'); return redirect(url_for('market_my'))

@app.route('/market/payment/callback')
@login_required
def market_payment_callback():
    tx_ref=clean(request.args.get('tx_ref') or request.args.get('reference')); transaction_id=clean(request.args.get('transaction_id') or request.args.get('id')); resp_raw=clean(request.args.get('resp'))
    if resp_raw:
        try:
            resp_obj=json.loads(resp_raw); resp_data=(resp_obj.get('data') or {}) if isinstance(resp_obj,dict) else {}
            tx_ref=tx_ref or clean(resp_data.get('tx_ref') or resp_data.get('txRef') or resp_data.get('reference')); transaction_id=transaction_id or clean(resp_data.get('id') or resp_data.get('transaction_id'))
        except Exception: logger.warning('Flutterwave callback resp could not be parsed')
    uid=(current_user() or {}).get('id'); tx=None
    if transaction_id:
        tx=_flutterwave_verify(transaction_id, tx_ref)
        if tx and not tx_ref: tx_ref=clean(tx.get('tx_ref') or tx.get('txRef') or tx.get('reference'))
    if not tx_ref: flash('Payment reference was missing. Check My Orders; Flutterwave webhook confirmation may still arrive.','warning'); return redirect(url_for('market_my'))
    orders=db_select('koja_market_orders',{'payment_reference':tx_ref,'buyer_id':uid},order='created_at.asc',limit=100) or []
    if not orders: flash('Market order not found.','danger'); return redirect(url_for('market_my'))
    if tx is None and transaction_id: tx=_flutterwave_verify(transaction_id, tx_ref)
    if tx:
        finalized=0
        for order in orders:
            if _finalize_market_order(order,tx): finalized+=1
        if finalized: flash(f'Payment verified. {finalized} KOJA Market order(s) confirmed.','success'); return redirect(url_for('market_my'))
    flash('Payment is still pending. KOJA will confirm it automatically when Flutterwave reports the successful transaction.','info'); return redirect(url_for('market_my'))

# Flutterwave V3 webhook: signature-authenticated, server-side re-verification and idempotent finalization.
@app.route('/webhook/flutterwave', methods=['POST'])
def flutterwave_webhook():
    if not FLW_SECRET_HASH:
        logger.error('Flutterwave webhook disabled: FLW_SECRET_HASH is not configured')
        return jsonify({'status':'disabled'}), 503
    raw=request.get_data(cache=True) or b''
    signature=clean(request.headers.get('flutterwave-signature'))
    legacy=clean(request.headers.get('verif-hash'))
    expected=base64.b64encode(hmac.new(FLW_SECRET_HASH.encode('utf-8'),raw,hashlib.sha256).digest()).decode('utf-8')
    valid_signature=bool(signature and hmac.compare_digest(expected,signature)) or bool(legacy and hmac.compare_digest(legacy,FLW_SECRET_HASH))
    if not valid_signature:
        logger.warning('Flutterwave webhook rejected: invalid signature')
        return jsonify({'status':'unauthorized'}),401
    payload=request.get_json(silent=True) or {}
    data=payload.get('data') or {}
    tx_ref=clean(data.get('tx_ref') or data.get('txRef') or data.get('reference') or payload.get('tx_ref') or payload.get('reference'))
    transaction_id=clean(data.get('id') or data.get('transaction_id') or payload.get('id') or payload.get('transaction_id'))
    logger.info('Flutterwave webhook received tx_ref=%s transaction_id=%s',tx_ref,transaction_id)
    if not tx_ref or not transaction_id:
        logger.warning('Flutterwave webhook ignored: missing reference or transaction id')
        return jsonify({'status':'ignored','reason':'missing_reference_or_transaction_id'}),200
    tx=_flutterwave_verify(transaction_id, tx_ref)
    if not tx:
        logger.warning('Flutterwave webhook pending: verification unavailable tx_ref=%s id=%s',tx_ref,transaction_id)
        return jsonify({'status':'pending','reason':'verification_unavailable'}),200
    verified_ref=clean(tx.get('tx_ref') or tx.get('txRef') or tx.get('reference'))
    if verified_ref != tx_ref:
        logger.error('Flutterwave webhook rejected: reference mismatch webhook=%s verified=%s',tx_ref,verified_ref)
        return jsonify({'status':'ignored','reason':'reference_mismatch'}),200
    market_orders=db_select('koja_market_orders',{'payment_reference':tx_ref},order='created_at.asc',limit=100) or []
    marketplace_order=first_row('koja_marketplace_orders',{'payment_reference':tx_ref})
    monetization_order=_mono_order_for_ref(tx_ref)
    if not market_orders and not marketplace_order and not monetization_order:
        logger.warning('Flutterwave webhook unknown reference tx_ref=%s',tx_ref)
        return jsonify({'status':'ignored','reason':'unknown_reference'}),200
    results=[]
    if market_orders:
        ok_count=0
        for market_order in market_orders:
            ok=_finalize_market_order(market_order,tx)
            logger.info('KOJA Market finalization tx_ref=%s order=%s result=%s',tx_ref,market_order.get('id'),ok)
            if ok: ok_count+=1
        results.append('market:'+str(ok_count)+'_finalized')
    if marketplace_order:
        ok=_finalize_marketplace_order(marketplace_order,tx)
        logger.info('KOJA Digital finalization tx_ref=%s order=%s result=%s',tx_ref,marketplace_order.get('id'),ok)
    if monetization_order:
        ok=_finalize_monetization(monetization_order,tx)
        logger.info('KOJA monetization finalization tx_ref=%s order=%s result=%s',tx_ref,monetization_order.get('id'),ok)
        results.append('monetization:'+('finalized_or_paid' if ok else 'failed'))
        results.append('digital:'+('finalized_or_paid' if ok else 'failed'))
    return jsonify({'status':'ok','processed':results}),200

@app.route('/market/sell',methods=['GET','POST'])
@login_required
def market_sell():
    seller=market_seller((current_user() or {}).get('id'))
    if not seller or str(seller.get('approval_status') or '').lower() not in {'approved','active'}:
        flash('Become an approved KOJA Market seller first.','warning'); return redirect(url_for('market_seller_register'))
    if request.method=='POST':
        title=clean(request.form.get('title')); desc=clean(request.form.get('description')); category=clean(request.form.get('category')) or 'Other'; ptype=clean(request.form.get('product_type')) or 'physical'
        try: price=float(request.form.get('price') or 0); stock=max(0,int(request.form.get('stock') or 0))
        except Exception: price=-1; stock=0
        if not title or price<0 or ptype not in KOJA_MARKET_TYPES: flash('Title, product type and valid price are required.','danger'); return redirect(url_for('market_sell'))
        if category not in KOJA_MARKET_CATEGORIES: category='Other'
        image=request.files.get('image'); image_url=None
        if image and image.filename:
            ext=image.filename.lower().rsplit('.',1)[-1] if '.' in image.filename else ''
            if ext not in {'jpg','jpeg','png','webp'}: flash('Product image must be JPG, JPEG, PNG or WEBP.','danger'); return redirect(url_for('market_sell'))
            up,err=upload_storage(image,'koja-market/products',public=False)
            if err: flash('Image upload failed: '+str(err)[:300],'danger'); return redirect(url_for('market_sell'))
            image_url=(up or {}).get('path')
        digital_url=None; digital_name=None
        if ptype=='digital':
            f=request.files.get('digital_file')
            if not f or not f.filename: flash('Choose the digital product file.','danger'); return redirect(url_for('market_sell'))
            up,err=upload_storage(f,'koja-market/digital',public=False)
            if err: flash('Digital file upload failed: '+str(err)[:300],'danger'); return redirect(url_for('market_sell'))
            digital_url=(up or {}).get('path'); digital_name=f.filename; stock=999999
        payload={'seller_id':seller.get('user_id'),'title':title,'description':desc,'category':category,'product_type':ptype,'price':price,'currency':'ZMW','stock':stock,'sku':clean(request.form.get('sku')) or None,'image_url':image_url,'digital_file_url':digital_url,'digital_file_name':digital_name,'delivery_available':bool(request.form.get('delivery_available')),'delivery_fee':float(request.form.get('delivery_fee') or 0) if ptype=='physical' else 0,'location':clean(request.form.get('location')),'is_published':False,'approval_status':'pending','created_at':utc_now(),'updated_at':utc_now()}
        _,err=db_insert('koja_market_products',payload)
        if err:
            if image_url: delete_storage_path(image_url)
            if digital_url: delete_storage_path(digital_url)
            flash('Product could not be saved. Run KOJA_MARKET.sql in Supabase.','danger')
        else: flash('Product submitted for KOJA Market approval.','success')
        return redirect(url_for('market_my'))
    return render_page('Sell on KOJA Market',r'''
<div class="hero"><h1>🏪 Sell on KOJA Market</h1><p>List physical or digital products. Approved sellers can reach customers across Africa.</p></div><div class="card"><form method="post" enctype="multipart/form-data"><label>Product title</label><input name="title" maxlength="180" required><label>Description</label><textarea name="description" maxlength="10000" required></textarea><div class="grid"><div><label>Type</label><select name="product_type" id="marketType"><option value="physical">Physical product</option><option value="digital">Digital product</option></select></div><div><label>Category</label><select name="category">{% for c in categories %}<option>{{ c }}</option>{% endfor %}</select></div><div><label>Price (ZMW)</label><input name="price" type="number" min="0" step="0.01" required></div><div><label>Stock</label><input name="stock" type="number" min="0" value="1"></div></div><label>SKU (optional)</label><input name="sku"><label>Product image</label><input type="file" name="image" accept="image/jpeg,image/png,image/webp"><div id="digitalFields" style="display:none"><label>Digital file</label><input type="file" name="digital_file"></div><label>Location</label><input name="location" placeholder="City / town / area"><label>Delivery fee (ZMW)</label><input name="delivery_fee" type="number" min="0" step="0.01" value="0"><label><input type="checkbox" name="delivery_available" checked style="width:auto"> Delivery available</label><button class="btn" type="submit">📤 Submit Listing</button></form></div><script>const t=document.getElementById('marketType'),d=document.getElementById('digitalFields');t.onchange=()=>d.style.display=t.value==='digital'?'block':'none';</script>
''',categories=KOJA_MARKET_CATEGORIES)

@app.route('/market/seller/register',methods=['GET','POST'])
@login_required
def market_seller_register():
    uid=(current_user() or {}).get('id'); existing=market_seller(uid)
    if request.method=='POST':
        name=clean(request.form.get('store_name')); desc=clean(request.form.get('description')); phone=clean(request.form.get('phone')); location=clean(request.form.get('location'))
        if not name: flash('Store name is required.','danger'); return redirect(url_for('market_seller_register'))
        payload={'user_id':uid,'store_name':name,'description':desc,'phone':phone,'location':location,'approval_status':'pending','is_active':True,'updated_at':utc_now()}
        if existing: _,err=db_update('koja_market_sellers',{'id':existing.get('id')},payload)
        else: _,err=db_insert('koja_market_sellers',payload)
        flash('Seller application submitted for approval.' if not err else 'Seller application could not be saved. Run KOJA_MARKET.sql in Supabase.','success' if not err else 'danger'); return redirect(url_for('market_my'))
    return render_page('Become a KOJA Market Seller',r'''<div class="hero"><h1>🏪 Become a Seller</h1><p>Create your KOJA Market store. Administrator approval protects buyers and the marketplace.</p></div><div class="card"><form method="post"><label>Store name</label><input name="store_name" value="{{ seller.store_name if seller else '' }}" required><label>Store description</label><textarea name="description">{{ seller.description if seller else '' }}</textarea><label>Phone</label><input name="phone" value="{{ seller.phone if seller else user.phone or '' }}" required><label>Location</label><input name="location" value="{{ seller.location if seller else '' }}"><button class="btn" type="submit">Submit Seller Application</button></form></div>''',seller=existing,user=current_user())

@app.route('/market/my')
@login_required
def market_my():
    uid=(current_user() or {}).get('id'); seller=market_seller(uid); products=db_select('koja_market_products',{'seller_id':uid},order='created_at.desc',limit=200) or []; purchases=db_select('koja_market_orders',{'buyer_id':uid},order='created_at.desc',limit=200) or []; sales=db_select('koja_market_orders',{'seller_id':uid},order='created_at.desc',limit=200) or []
    ids={str(o.get('product_id')) for o in purchases+sales if o.get('product_id')}; ps=db_select('koja_market_products',{'id':'in.('+','.join(ids)+')'} if ids else {'id':'eq.__none__'},limit=300) or []; pm={str(x.get('id')):x for x in ps}
    return render_page('My KOJA Market',r'''<div class="hero"><h1>📦 Seller Dashboard</h1><p>Seller status: <strong>{{ seller.approval_status if seller else 'Not registered' }}</strong></p><div class="actions"><a class="btn" href="{{ url_for('market_sell') }}">➕ Add Product</a><a class="btn secondary" href="{{ url_for('market_seller_register') }}">🏬 My Store</a><a class="btn secondary" href="{{ url_for('seller_verification') }}">✓ Seller Verification</a><a class="btn secondary" href="{{ url_for('market_seller_subscription') }}">💎 Seller Subscription</a><a class="btn secondary" href="{{ url_for('market_advertise') }}">📣 Advertising</a><a class="btn secondary" href="{{ url_for('market_earnings') }}">📊 Earnings & Analytics</a><a class="btn secondary" href="{{ url_for('seller_wallet') }}">💰 Wallet</a><a class="btn secondary" href="{{ url_for('market_seller_payouts') }}">💸 Payouts</a><a class="btn secondary" href="{{ url_for('market_coupons') }}">🏷️ Coupons</a><a class="btn secondary" href="{{ url_for('referrals') }}">🤝 Referrals</a><a class="btn secondary" href="{{ '/market' }}">🛍️ Browse Market</a></div></div><div class="card"><h2>My Listings</h2><p class="small">Feature any of your products for K5 per day (1–30 days). Requests are sent for approval.</p><table><tr><th>Product</th><th>Price</th><th>Stock</th><th>Status</th><th>Featured</th></tr>{% for p in products %}<tr><td><a href="{{ url_for('market_product_view',product_id=p.id) }}">{{ p.title }}</a></td><td>{{ money(p.price,p.currency) }}</td><td>{{ p.stock }}</td><td>{{ p.approval_status }}</td><td><form method="post" action="{{ url_for('market_feature_product',product_id=p.id) }}" style="display:flex;gap:6px;align-items:center"><input name="days" type="number" min="1" max="30" value="7" style="max-width:80px"><button class="btn" type="submit">⭐ Feature</button></form></td></tr>{% else %}<tr><td colspan="5">No listings. <a href="{{ url_for('market_sell') }}">List your first product</a>.</td></tr>{% endfor %}</table></div><div class="card"><h2>My Purchases</h2><table><tr><th>Order</th><th>Product</th><th>Total</th><th>Status</th></tr>{% for o in purchases %}<tr><td>{{ o.order_number }}</td><td>{{ pm.get(o.product_id,{}).get('title','Product') }}</td><td>{{ money(o.total_amount,o.currency) }}</td><td>{{ o.status }}</td></tr>{% else %}<tr><td colspan="4">No purchases.</td></tr>{% endfor %}</table></div>{% if seller %}<div class="card"><h2>Sales</h2><table><tr><th>Order</th><th>Product</th><th>Total</th><th>KOJA commission</th><th>Status</th></tr>{% for o in sales %}<tr><td>{{ o.order_number }}</td><td>{{ pm.get(o.product_id,{}).get('title','Product') }}</td><td>{{ money(o.total_amount,o.currency) }}</td><td>{{ money(o.commission_amount,o.currency) }}</td><td>{{ o.status }}</td></tr>{% else %}<tr><td colspan="5">No sales yet.</td></tr>{% endfor %}</table></div>{% endif %}''',seller=seller,products=products,purchases=purchases,sales=sales,pm=pm,money=market_money)

@app.route('/admin/market',methods=['GET','POST'])
@admin_required
def admin_market():
    if request.method=='POST':
        action=clean(request.form.get('action')); iid=clean(request.form.get('item_id')); kind=clean(request.form.get('kind'))
        if kind=='seller': db_update('koja_market_sellers',{'id':iid},{'approval_status':'approved' if action=='approve' else 'rejected','is_active':action=='approve','updated_at':utc_now()}); flash('Seller status updated.','success')
        elif kind=='product': db_update('koja_market_products',{'id':iid},{'approval_status':'approved' if action=='approve' else 'rejected','is_published':action=='approve','updated_at':utc_now()}); flash('Product status updated.','success')
        elif kind=='order': db_update('koja_market_orders',{'id':iid},{'status':action,'updated_at':utc_now()}); flash('Order status updated.','success')
        return redirect(url_for('admin_market'))
    sellers=db_select('koja_market_sellers',order='created_at.desc',limit=300) or []; products=db_select('koja_market_products',order='created_at.desc',limit=300) or []; orders=db_select('koja_market_orders',order='created_at.desc',limit=300) or []
    return render_page('KOJA Market Admin',r'''<div class="hero"><h1>🛡️ KOJA Market Admin</h1><p>Approve sellers/products and monitor orders and KOJA commission.</p></div><div class="card"><h2>Seller Applications</h2><table><tr><th>Store</th><th>Location</th><th>Status</th><th>Action</th></tr>{% for s in sellers %}<tr><td>{{ s.store_name }}</td><td>{{ s.location }}</td><td>{{ s.approval_status }}</td><td>{% if s.approval_status!='approved' %}<form method="post"><input type="hidden" name="kind" value="seller"><input type="hidden" name="item_id" value="{{ s.id }}"><button class="btn success" name="action" value="approve">Approve</button><button class="btn danger" name="action" value="reject">Reject</button></form>{% endif %}</td></tr>{% else %}<tr><td colspan="4">No seller applications.</td></tr>{% endfor %}</table></div><div class="card"><h2>Products</h2><table><tr><th>Product</th><th>Type</th><th>Price</th><th>Status</th><th>Action</th></tr>{% for p in products %}<tr><td>{{ p.title }}</td><td>{{ p.product_type }}</td><td>{{ money(p.price,p.currency) }}</td><td>{{ p.approval_status }}</td><td>{% if p.approval_status!='approved' %}<form method="post"><input type="hidden" name="kind" value="product"><input type="hidden" name="item_id" value="{{ p.id }}"><button class="btn success" name="action" value="approve">Approve</button><button class="btn danger" name="action" value="reject">Reject</button></form>{% endif %}</td></tr>{% else %}<tr><td colspan="5">No products.</td></tr>{% endfor %}</table></div><div class="card"><h2>Orders</h2><table><tr><th>Order</th><th>Total</th><th>KOJA commission</th><th>Status</th><th>Action</th></tr>{% for o in orders %}<tr><td>{{ o.order_number }}</td><td>{{ money(o.total_amount,o.currency) }}</td><td>{{ money(o.commission_amount,o.currency) }}</td><td>{{ o.status }}</td><td>{% if o.status=='paid' %}<form method="post"><input type="hidden" name="kind" value="order"><input type="hidden" name="item_id" value="{{ o.id }}"><button class="btn success" name="action" value="processing">Processing</button><button class="btn" name="action" value="shipped">Shipped</button><button class="btn" name="action" value="completed">Completed</button></form>{% endif %}</td></tr>{% else %}<tr><td colspan="5">No orders.</td></tr>{% endfor %}</table></div>''',sellers=sellers,products=products,orders=orders,money=market_money)

@app.route('/market/cart')
@login_required
def market_cart():
 uid=(current_user() or {}).get('id'); carts=db_select('koja_market_cart',{'user_id':uid},limit=100) or []; ids=[str(x.get('product_id')) for x in carts if x.get('product_id')]; ps=db_select('koja_market_products',{'id':'in.('+','.join(ids)+')'} if ids else {},limit=200) or []; pm={str(x.get('id')):x for x in ps}; items=[]; total=0
 for c in carts:
  p=pm.get(str(c.get('product_id')))
  if not p: continue
  q=max(1,int(c.get('quantity') or 1)); line=float(p.get('price') or 0)*q; total+=line; items.append({'product':p,'quantity':q,'line':line})
 return render_page('KOJA Market Cart',"""<div class='hero'><h1>My Cart</h1><p>Review your items before checkout.</p><a class='btn secondary' href='{{ '/market' }}'>Continue Shopping</a></div><div class='card'>{% for x in items %}<div style='padding:14px 0;border-bottom:1px solid var(--border)'><strong>{{ x.product.title }}</strong><p>{{ money(x.product.price,x.product.currency) }} x {{ x.quantity }} = {{ money(x.line,x.product.currency) }}</p><form method='post' action='{{ url_for('market_cart_remove',product_id=x.product.id) }}'><button class='btn danger'>Remove</button></form></div>{% else %}<p>Your cart is empty.</p>{% endfor %}{% if items %}<h2>Total: {{ money(total,'ZMW') }}</h2><a class='btn' href='{{ url_for('market_cart_checkout') }}'>Secure Checkout</a>{% endif %}</div>""",items=items,total=total,money=market_money)

@app.route('/market/cart/add/<product_id>',methods=['POST'])
@login_required
def market_cart_add(product_id):
 uid=(current_user() or {}).get('id'); p=market_product(product_id)
 if not p or not as_bool(p.get('is_published')) or str(p.get('approval_status') or '').lower() not in {'approved','active'}: abort(404)
 try:q=max(1,int(request.form.get('quantity') or 1))
 except:q=1
 ex=first_row('koja_market_cart',{'user_id':uid,'product_id':product_id})
 if ex: _,err=db_update('koja_market_cart',{'id':ex.get('id')},{'quantity':int(ex.get('quantity') or 0)+q,'updated_at':utc_now()})
 else: _,err=db_insert('koja_market_cart',{'user_id':uid,'product_id':product_id,'quantity':q,'created_at':utc_now(),'updated_at':utc_now()})
 flash('Added to cart.' if not err else 'Could not update cart.','success' if not err else 'danger'); return redirect(url_for('market_cart'))

@app.route('/market/cart/remove/<product_id>',methods=['POST'])
@login_required
def market_cart_remove(product_id):
 db_delete('koja_market_cart',{'user_id':(current_user() or {}).get('id'),'product_id':product_id}); return redirect(url_for('market_cart'))

@app.route('/market/store/<seller_id>')
def market_store(seller_id):
 seller=market_seller(seller_id) or first_row('koja_market_sellers',{'id':seller_id})
 if not seller: abort(404)
 products=db_select('koja_market_products',{'seller_id':seller.get('user_id'),'is_published':'eq.true'},order='created_at.desc',limit=100) or []
 return render_page('KOJA Store',"""<div class='hero'><h1>{{ seller.store_name }}</h1><p>{{ seller.description or 'KOJA Market seller store' }}</p><p>{{ seller.location or '' }}</p></div><div class='grid'>{% for p in products %}<div class='card'><h3>{{ p.title }}</h3><p>{{ p.category }}</p><h3>{{ money(p.price,p.currency) }}</h3><a class='btn' href='{{ url_for('market_product_view',product_id=p.id) }}'>View</a></div>{% else %}<div class='card'>No active products.</div>{% endfor %}</div>""",seller=seller,products=products,money=market_money)

@app.route('/market/wishlist')
@login_required
def market_wishlist():
 uid=(current_user() or {}).get('id'); ws=db_select('koja_market_wishlist',{'user_id':uid},limit=100) or []; ids=[str(x.get('product_id')) for x in ws if x.get('product_id')]; products=db_select('koja_market_products',{'id':'in.('+','.join(ids)+')'} if ids else {'id':'eq.__none__'},limit=200) or []
 return render_page('KOJA Wishlist',"""<div class='hero'><h1>Wishlist</h1></div><div class='grid'>{% for p in products %}<div class='card'><h3>{{ p.title }}</h3><h3>{{ money(p.price,p.currency) }}</h3><a class='btn' href='{{ url_for('market_product_view',product_id=p.id) }}'>View</a></div>{% else %}<div class='card'>Wishlist is empty.</div>{% endfor %}</div>""",products=products,money=market_money)

@app.route('/market/wishlist/toggle/<product_id>',methods=['POST'])
@login_required
def market_wishlist_toggle(product_id):
 uid=(current_user() or {}).get('id'); ex=first_row('koja_market_wishlist',{'user_id':uid,'product_id':product_id})
 if ex: db_delete('koja_market_wishlist',{'id':ex.get('id')})
 else: db_insert('koja_market_wishlist',{'user_id':uid,'product_id':product_id})
 return redirect(url_for('market_product_view',product_id=product_id))

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
<div class="card"><h3>🎥 Video Call</h3>{% if connected %}<p>🟢 Connected — you can start a video call now.</p><a class="btn" href="{{ url_for('professional_call', provider_id=provider.id, mode='video') }}">Start Video Call</a>{% else %}<p>🔴 This professional is not connected right now.</p><button class="btn secondary" disabled>Video Call Unavailable</button>{% endif %}</div><div class="card"><h3>📲 Incoming Calls</h3><p>Professionals can open their call inbox to receive calls.</p><a class="btn secondary" href="{{ url_for('professional_calls') }}">Open Call Inbox</a></div>
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
async function startCall(){try{if(!navigator.onLine)throw Error('No internet connection'); const stream=await media(); document.getElementById('local').srcObject=stream; pc=new RTCPeerConnection({iceServers:[{urls:'stun:stun.l.google.com:19302'}]}); pc.onconnectionstatechange=()=>{if(pc && ['failed','disconnected'].includes(pc.connectionState)) failCall()}; stream.getTracks().forEach(t=>pc.addTrack(t,stream)); pc.ontrack=e=>{const st=e.streams[0];const v=document.getElementById('remote'),a=document.getElementById('remoteAudio');v.srcObject=st;a.srcObject=st;v.volume=1;a.volume=1;if(window.AudioContext||window.webkitAudioContext){try{const C=window.AudioContext||window.webkitAudioContext,ctx=new C(),src=ctx.createMediaStreamSource(st),gain=ctx.createGain(),dst=ctx.createMediaStreamDestination();gain.gain.value=1.8;src.connect(gain);gain.connect(dst);const boosted=new MediaStream([...st.getVideoTracks(),...dst.stream.getAudioTracks()]);v.srcObject=boosted;a.srcObject=boosted;v.play().catch(()=>{});a.play().catch(()=>{});}catch(_){} }}; pc.onicecandidate=e=>{if(e.candidate && callId)fetch('/api/professional/call/'+callId+'/ice',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({candidate:e.candidate.toJSON(),side:'caller'})}).catch(()=>{})}; const offer=await pc.createOffer(); await pc.setLocalDescription(offer); const r=await fetch('/api/professional/call/'+providerId,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({mode,offer:offer.sdp})}); const d=await r.json(); if(!r.ok)throw Error(d.error||'Call failed'); callId=d.call_id; state('Calling professional…'); callTimer=setTimeout(failCall,30000); poll=setInterval(checkCall,1000)}catch(e){if(e.message&&(/internet|network|failed|available/i.test(e.message))) tellUnavailable(); else state('Could not start call: '+e.message)}}
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
async function accept(){try{stream=await navigator.mediaDevices.getUserMedia({audio:true,video:mode==='video'});document.getElementById('local').srcObject=stream;pc=new RTCPeerConnection({iceServers:[{urls:'stun:stun.l.google.com:19302'}]});stream.getTracks().forEach(t=>pc.addTrack(t,stream));pc.ontrack=e=>{const st=e.streams[0],v=document.getElementById('remote'),a=document.getElementById('audio');v.srcObject=st;a.srcObject=st;v.volume=1;a.volume=1;if(window.AudioContext||window.webkitAudioContext){try{const C=window.AudioContext||window.webkitAudioContext,ctx=new C(),src=ctx.createMediaStreamSource(st),gain=ctx.createGain(),dst=ctx.createMediaStreamDestination();gain.gain.value=1.8;src.connect(gain);gain.connect(dst);const boosted=new MediaStream([...st.getVideoTracks(),...dst.stream.getAudioTracks()]);v.srcObject=boosted;a.srcObject=boosted;v.play().catch(()=>{});a.play().catch(()=>{});}catch(_){} }};pc.onicecandidate=e=>{if(e.candidate)fetch('/api/professional/call/'+id+'/ice',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({candidate:e.candidate.toJSON(),side:'callee'})})};const r=await fetch('/api/professional/call/'+id);const d=await r.json();await pc.setRemoteDescription({type:'offer',sdp:d.call.offer});const answer=await pc.createAnswer();await pc.setLocalDescription(answer);await fetch('/api/professional/call/'+id+'/answer',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({answer:answer.sdp})});state('Connected');setInterval(async()=>{const q=await fetch('/api/professional/call/'+id);const x=await q.json();for(const c of (x.call.caller_ice||[])){try{await pc.addIceCandidate(c)}catch(e){}}},1000)}catch(e){state('Could not accept call: '+e.message)}}
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
<a class="btn secondary" href="{{ url_for('track_delivery',tracking_code=d.get('tracking_code')) }}">Track Map</a>
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
        "sender_id":user["id"],
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
            "id":str(uuid.uuid4()),"customer_id":user["id"],"sender_id":user["id"],
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
    user=current_user() or {}
    allowed=bool(user.get("is_admin")) or str(delivery.get("customer_id") or "") == str(user.get("id") or "")
    if not allowed:
        provider=get_driver_provider(user.get("id"))
        allowed=bool(provider and str(provider.get("id")) == str(delivery.get("driver_id") or ""))
    if not allowed: abort(403)
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
    user=current_user() or {}
    provider=first_row("service_providers",{"id":provider_id}) or {}
    own_provider=provider.get("user_id") and str(provider.get("user_id"))==str(user.get("id") or "")
    if not user.get("is_admin") and not own_provider:
        # A provider map is private; only an admin or the provider themselves may open it.
        abort(403)
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
    user=current_user() or {}
    provider=first_row("service_providers",{"id":provider_id}) or {}
    own_provider=provider.get("user_id") and str(provider.get("user_id"))==str(user.get("id") or "")
    if not user.get("is_admin") and not own_provider:
        return jsonify({"ok":False,"message":"You are not authorized to view this provider location."}),403
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
    "/documents",
    "/marketplace",
    "/market",
    "/professionals",
    "/doctors",
    "/teachers",
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
@admin_required
def admin_marketplace():
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
<a class="btn success" href="{{ url_for('admin_market') }}">🛍️ KOJA Market</a>
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
            uploaded, error = upload_storage(pdf, "assignment-answers", public=False)
            if error:
                flash(f"PDF upload failed: {error}", "danger")
                return redirect(url_for("admin_assignment_answer", assignment_id=assignment_id))
            updates.update({
                "answer_file_name": uploaded["file_name"],
                "answer_file_path": uploaded["path"],
                "answer_file_url": uploaded["path"],
            })
        row, error = db_update("assignments", {"id": assignment_id}, updates)
        if error:
            if pdf and pdf.filename and uploaded:
                delete_storage_path(uploaded.get("path"))
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
create table if not exists public.koja_group_call_participants (call_id uuid not null references public.koja_calls(id) on delete cascade, user_id uuid not null, status text not null default 'invited', joined_at timestamptz, primary key(call_id,user_id));
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
"""

def _connect_user(uid): return find_user_by_id(uid) or {}
def _conversation_member(cid, uid): return bool(first_row('koja_conversation_members', {'conversation_id':cid,'user_id':uid}))
def _profile_name(uid):
    u=_connect_user(uid); return first_nonempty(u.get('full_name'),u.get('name'),u.get('email'),'KOJA User')
def _direct_conversation(a,b):
    rows=db_select('koja_conversation_members',filters={'user_id':a},limit=100)
    for m in rows:
        cid=m.get('conversation_id')
        if cid and _conversation_member(cid,b):
            c=first_row('koja_conversations',{'id':cid})
            if c and c.get('conversation_type','direct')=='direct': return c
    c,err=db_insert('koja_conversations',{'id':str(uuid.uuid4()),'conversation_type':'direct','created_by':a,'created_at':utc_now(),'updated_at':utc_now()})
    if err or not c:return None
    cid=c['id']; db_insert('koja_conversation_members',{'conversation_id':cid,'user_id':a,'role':'member','joined_at':utc_now()}); db_insert('koja_conversation_members',{'conversation_id':cid,'user_id':b,'role':'member','joined_at':utc_now()}); return c

@app.route('/connect')
@login_required
def connect():
    uid=current_user()['id']; members=db_select('koja_conversation_members',filters={'user_id':uid},limit=100); conversations=[]
    for m in members:
        c=first_row('koja_conversations',{'id':m.get('conversation_id')})
        if not c: continue
        others=db_select('koja_conversation_members',filters={'conversation_id':c['id']},limit=10); other=next((x for x in others if str(x.get('user_id'))!=str(uid)),None)
        c['_other_name']=_profile_name(other['user_id']) if other else (c.get('name') or 'Group'); last=db_select('koja_messages',filters={'conversation_id':c['id']},order='created_at.desc',limit=1); c['_last']=(last[0].get('body') or last[0].get('message_type','')) if last else 'No messages yet'; conversations.append(c)
    return render_page('KOJA Connect',r'''<div class="hero"><h2>💬 KOJA Connect</h2><p>Chat, voice messages, voice calls, video calls, photos, files, groups and status updates with other KOJA users.</p></div><div class="grid"><div class="card"><h3>👥 Find People</h3><p>Search KOJA users and start a conversation.</p><a class="btn" href="{{ url_for('connect_people') }}">Find People</a></div><div class="card"><h3>🟢 Status</h3><p>Share a 24-hour status.</p><a class="btn" href="{{ url_for('connect_status') }}">My Status</a></div><div class="card"><h3>📞 Calls</h3><p>Voice and video calls separate from Professional Services.</p><a class="btn" href="{{ url_for('connect_calls') }}">Call History</a></div></div><div class="card"><div class="actions"><h3 style="margin-right:auto">Recent Chats</h3><a class="btn" href="{{ url_for('connect_group_new') }}">➕ New Group</a></div>{% for c in conversations %}<a class="card" style="display:block;text-decoration:none;color:inherit" href="{{ url_for('connect_chat',conversation_id=c.id) }}"><strong>{{ c._other_name }}</strong><div class="small">{{ c._last }}</div></a>{% else %}<p>No chats yet. Find a KOJA user to start.</p>{% endfor %}</div>''',conversations=conversations)

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
    return render_page('KOJA Chat',r'''<div class="card"><a href="{{ url_for('connect') }}">← Connect</a><h2>💬 {{ name }}</h2><p class="small">Sent messages appear on the right. Received messages appear on the left.</p></div><div class="card" id="messages" style="min-height:300px;max-height:55vh;overflow:auto"></div><div class="card"><form id="sendForm"><input id="text" autocomplete="off" placeholder="Write a message…"><button>Send</button></form><form id="fileForm" enctype="multipart/form-data" style="margin-top:8px"><input id="file" type="file" accept="image/*,.pdf,.doc,.docx,.txt,.webp,.audio/*"><button type="submit">📎 Photo / File</button></form><div class="grid"><button type="button" id="voiceNote">🎙️ Voice message</button><a class="btn" href="{{ url_for('connect_call',user_id=other_id,mode='voice') }}">📞 Voice Call</a><a class="btn" href="{{ url_for('connect_call',user_id=other_id,mode='video') }}">🎥 Video Call</a>{% if c.get('conversation_type')=='group' %}<a class="btn" href="{{ url_for('connect_group_call',conversation_id=conversation_id,mode='video') }}">👥 Group Video</a><a class="btn secondary" href="{{ url_for('connect_group_call',conversation_id=conversation_id,mode='voice') }}">👥 Group Voice</a>{% endif %}</div></div><script>const cid={{ conversation_id|tojson }},me={{ user.id|tojson }};const box=document.getElementById('messages'),text=document.getElementById('text');function esc(v){return String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}async function load(){let r=await fetch('/api/connect/messages/'+cid);if(!r.ok)return;let d=await r.json();box.innerHTML=d.messages.map(m=>{let mine=String(m.sender_id)===String(me);let body=m.message_type==='text'?'<div>'+esc(m.body)+'</div>':(m.file_url?'<div><a target="_blank" rel="noopener" href="'+esc(m.file_url)+'">'+esc(m.body||m.message_type)+'</a></div>':'<div>'+esc(m.body)+'</div>');return '<div style="display:flex;justify-content:'+(mine?'flex-end':'flex-start')+';margin:7px 0"><div style="max-width:78%;padding:10px 13px;border-radius:16px;background:var(--card);border:1px solid var(--border);text-align:left"><strong>'+esc(mine?'You':m.sender_name)+'</strong>'+body+'<div class="small">'+esc(m.created_at||'')+'</div></div></div>'}).join('');box.scrollTop=box.scrollHeight;}document.getElementById('sendForm').onsubmit=async e=>{e.preventDefault();let v=text.value.trim();if(!v)return;let r=await fetch('/api/connect/messages/'+cid,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:v})});if(r.ok){text.value='';load();}};document.getElementById('fileForm').onsubmit=async e=>{e.preventDefault();let f=document.getElementById('file').files[0];if(!f)return;let fd=new FormData();fd.append('file',f);let r=await fetch('/api/connect/messages/'+cid+'/upload',{method:'POST',body:fd});if(r.ok){document.getElementById('file').value='';load();}else alert('File could not be sent.');};load();setInterval(load,2000);let rec,parts=[];document.getElementById('voiceNote').onclick=async()=>{try{let st=await navigator.mediaDevices.getUserMedia({audio:true});rec=new MediaRecorder(st);parts=[];rec.ondataavailable=e=>parts.push(e.data);rec.onstop=async()=>{let b=new Blob(parts,{type:'audio/webm'}),fd=new FormData();fd.append('file',b,'voice.webm');await fetch('/api/connect/messages/'+cid+'/upload',{method:'POST',body:fd});st.getTracks().forEach(t=>t.stop());load();};rec.start();setTimeout(()=>rec&&rec.state==='recording'&&rec.stop(),60000);}catch(e){alert('Microphone permission is required.');}};</script>''',conversation_id=conversation_id,name=_profile_name(other_id) if other_id else c.get('name','KOJA Chat'),c=c)

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
    for m in rows:
        m['sender_name']=_profile_name(m.get('sender_id'))
        if m.get('file_url'):
            m['file_url']=url_for('connect_message_media', message_id=m.get('id'))
    return jsonify(messages=rows)

@app.route('/api/connect/messages/<conversation_id>/upload',methods=['POST'])
@login_required
def connect_upload(conversation_id):
    uid=current_user()['id']
    if not _conversation_member(conversation_id,uid):return jsonify(error='Forbidden'),403
    f=request.files.get('file')
    if not f or not f.filename:return jsonify(error='No file'),400
    data=f.read()
    if len(data)>15*1024*1024:return jsonify(error='File too large (15 MB maximum)'),413
    name=secure_filename(f.filename) or ('upload-'+uuid.uuid4().hex); ext=os.path.splitext(name)[1].lower()
    allowed={'.webm','.wav','.mp3','.m4a','.ogg','.jpg','.jpeg','.png','.webp','.pdf','.doc','.docx','.txt'}
    if ext not in allowed:return jsonify(error='Unsupported file type'),400
    mime=f.mimetype or 'application/octet-stream'; path=f'connect/files/{uuid.uuid4().hex}{ext}'
    r=requests.post(sb_storage_url(path),headers=sb_headers({'Content-Type':mime,'x-upsert':'true'}),data=data,timeout=60)
    if not r.ok:return jsonify(error=r.text[:500]),500
    mt='audio' if mime.startswith('audio/') else ('image' if mime.startswith('image/') else 'file')
    row,err=db_insert('koja_messages',{'id':str(uuid.uuid4()),'conversation_id':conversation_id,'sender_id':uid,'message_type':mt,'file_url':path,'body':name if mt!='audio' else 'Voice message','created_at':utc_now()})
    if err:
        delete_storage_path(path)
        return jsonify(error=err),500
    if row and row.get('file_url'):
        row['file_url']=url_for('connect_message_media', message_id=row.get('id'))
    return jsonify(message=row)

def _storage_path_from_value(value):
    value=clean(value)
    if not value:
        return ''
    public_prefix=f"{SUPABASE_URL.rstrip('/')}/storage/v1/object/public/{quote(STORAGE_BUCKET, safe='')}/" if SUPABASE_URL else ''
    if public_prefix and value.startswith(public_prefix):
        return unquote(value[len(public_prefix):])
    if value.startswith('http://') or value.startswith('https://'):
        return ''
    path=value.lstrip('/')
    if path.startswith(f"{STORAGE_BUCKET}/"):
        path=path[len(STORAGE_BUCKET)+1:]
    return path

@app.route('/connect/media/<message_id>')
@login_required
def connect_message_media(message_id):
    uid=current_user()['id']
    msg=first_row('koja_messages',{'id':message_id})
    if not msg or not _conversation_member(msg.get('conversation_id'),uid): abort(404)
    path=_storage_path_from_value(msg.get('file_url'))
    if not path or not supabase_configured(): abort(404)
    try:
        r=requests.get(sb_storage_url(path),headers=sb_headers(),timeout=30)
        if not r.ok: abort(404)
        filename=secure_filename(msg.get('body') or 'koja-connect-file') or 'koja-connect-file'
        response=send_file(io.BytesIO(r.content),download_name=filename,mimetype=r.headers.get('Content-Type') or 'application/octet-stream',as_attachment=not str(msg.get('message_type') or '').lower()=='image',max_age=0)
        response.headers['Cache-Control']='private, no-store'
        response.headers['X-Content-Type-Options']='nosniff'
        return response
    except Exception:
        logger.exception('KOJA Connect media read failed')
        abort(404)


def _is_accepted_contact(a,b):
    if not a or not b or str(a)==str(b):
        return False
    return bool(first_row('koja_contacts',{'requester_id':a,'addressee_id':b,'status':'accepted'}) or first_row('koja_contacts',{'requester_id':b,'addressee_id':a,'status':'accepted'}))

@app.route('/connect/status/media/<status_id>')
@login_required
def connect_status_media_file(status_id):
    uid=current_user()['id']
    status=first_row('koja_statuses',{'id':status_id})
    if not status: abort(404)
    owner=str(status.get('user_id') or '')
    if owner!=str(uid) and (str(status.get('visibility') or 'contacts').lower()=='contacts' and not _is_accepted_contact(uid,owner)):
        abort(404)
    expires=status.get('expires_at')
    try:
        if expires and datetime.fromisoformat(str(expires).replace('Z','+00:00')) <= datetime.now(timezone.utc): abort(404)
    except Exception:
        pass
    path=_storage_path_from_value(status.get('media_url'))
    if not path or not supabase_configured(): abort(404)
    try:
        r=requests.get(sb_storage_url(path),headers=sb_headers(),timeout=30)
        if not r.ok: abort(404)
        response=send_file(io.BytesIO(r.content),download_name='koja-status-media',mimetype=r.headers.get('Content-Type') or 'application/octet-stream',as_attachment=False,max_age=0)
        response.headers['Cache-Control']='private, no-store'
        response.headers['X-Content-Type-Options']='nosniff'
        return response
    except Exception:
        logger.exception('KOJA status media read failed')
        abort(404)

@app.route('/connect/group/new',methods=['GET','POST'])
@login_required
def connect_group_new():
    uid=current_user()['id']
    if request.method=='POST':
        name=clean(request.form.get('name')) or 'KOJA Group'; ids=list(dict.fromkeys([x for x in request.form.getlist('user_id') if x and x!=uid]))
        if not ids:return redirect(url_for('connect_group_new'))
        c,err=db_insert('koja_conversations',{'id':str(uuid.uuid4()),'conversation_type':'group','created_by':uid,'name':name,'created_at':utc_now(),'updated_at':utc_now()})
        if err:return 'Could not create group: '+str(err),500
        for member in [uid]+ids:
            if find_user_by_id(member):db_insert('koja_conversation_members',{'conversation_id':c['id'],'user_id':member,'role':'admin' if member==uid else 'member','joined_at':utc_now()})
        return redirect(url_for('connect_chat',conversation_id=c['id']))
    q=clean(request.args.get('q')); people=[]
    if q:
        for col in ('email','full_name','name'):
            for x in db_select('profiles',filters={col:f'ilike.*{q}*'},limit=30):
                if str(x.get('id'))!=str(uid) and not any(str(p.get('id'))==str(x.get('id')) for p in people):people.append(x)
    return render_page('New KOJA Group',r'''<div class="card"><h2>👥 Create KOJA Group</h2><form method="get"><input name="q" value="{{ q }}" placeholder="Search people"><button>Search</button></form><form method="post"><input name="name" placeholder="Group name" required>{% for p in people %}<label style="display:block;margin:10px 0"><input type="checkbox" name="user_id" value="{{ p.id }}"> {{ p.get('full_name') or p.get('name') or p.get('email') }}</label>{% endfor %}<button class="btn">Create Group</button></form></div>''',people=people,q=q)

@app.route('/connect/group-call/<conversation_id>')
@login_required
def connect_group_call(conversation_id):
    uid=current_user()['id']; mode=clean(request.args.get('mode','video'))
    if mode not in ('voice','video') or not _conversation_member(conversation_id,uid):abort(403)
    return render_page('KOJA Group Call',r'''<div class="card"><h2>👥 KOJA Group {{ mode|title }} Call</h2><p>Start a group call invitation for all members.</p><div id="state">Ready</div><button id="start" class="btn">Start Group Call</button><button id="hang" class="btn danger">End</button></div><script>const cid={{ conversation_id|tojson }},mode={{ mode|tojson }};let calls=[];start.onclick=async()=>{let r=await fetch('/api/connect/group-call/create',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({conversation_id:cid,mode})}),d=await r.json();if(!r.ok){state.textContent=d.error||'Could not start';return}calls=d.calls||[];state.textContent='Invited '+calls.length+' participant(s).';};hang.onclick=async()=>{for(const c of calls)await fetch('/api/connect/call/end/'+c.id,{method:'POST'});state.textContent='Group call ended';};</script>''',conversation_id=conversation_id,mode=mode)

@app.route('/api/connect/group-call/create',methods=['POST'])
@login_required
def connect_group_call_create():
    uid=current_user()['id']; d=request.get_json(silent=True) or {}; cid=clean(d.get('conversation_id')); mode=d.get('mode','video')
    if mode not in ('voice','video') or not _conversation_member(cid,uid):return jsonify(error='Forbidden'),403
    members=db_select('koja_conversation_members',filters={'conversation_id':cid},limit=50); calls=[]
    for m in members:
        callee=m.get('user_id')
        if not callee or str(callee)==str(uid):continue
        row,err=db_insert('koja_calls',{'id':str(uuid.uuid4()),'conversation_id':cid,'caller_id':uid,'callee_id':callee,'mode':mode,'status':'ringing','created_at':utc_now()})
        if not err and row:
            db_insert('koja_group_call_participants',{'call_id':row['id'],'user_id':callee,'status':'invited'})
            db_insert('koja_notifications',{'user_id':callee,'notification_type':'group_call','title':f'Incoming group {mode} call','body':f'{_profile_name(uid)} started a group call.','related_id':row['id']});calls.append(row)
    return jsonify(calls=calls)

@app.route('/connect/status',methods=['GET','POST'])
@login_required
def connect_status():
    uid=current_user()['id']
    if request.method=='POST':
        body=clean(request.form.get('text'))
        if body:db_insert('koja_statuses',{'id':str(uuid.uuid4()),'user_id':uid,'text_content':body,'media_type':'text','visibility':'contacts','expires_at':(datetime.now(timezone.utc)+timedelta(hours=24)).isoformat(),'created_at':utc_now()});flash('Status posted for 24 hours.','success')
        return redirect(url_for('connect_status'))
    rows=db_select('koja_statuses',filters={'user_id':uid},order='created_at.desc',limit=30)
    return render_page('KOJA Status',r'''<div class="card"><h2>🟢 My Status</h2><form method="post"><textarea name="text" maxlength="1000" placeholder="Share an update…"></textarea><button>Post Status</button></form><form method="post" enctype="multipart/form-data" action="{{ url_for('connect_status_media') }}"><input type="file" name="file" accept="image/*,video/*"><button>📷 Photo / Video Status</button></form></div>{% for s in rows %}<div class="card"><strong>{{ s.text_content }}</strong><div class="small">Expires: {{ s.expires_at }}</div></div>{% endfor %}''',rows=rows)

@app.route('/connect/status/media',methods=['POST'])
@login_required
def connect_status_media():
    uid=current_user()['id']; f=request.files.get('file')
    if not f or not f.filename:return redirect(url_for('connect_status'))
    data=f.read(); name=secure_filename(f.filename) or 'status'; ext=os.path.splitext(name)[1].lower()
    if len(data)>15*1024*1024 or ext not in {'.jpg','.jpeg','.png','.webp','.mp4','.webm'}:return redirect(url_for('connect_status'))
    mime=f.mimetype or 'application/octet-stream'; path=f'connect/status/{uuid.uuid4().hex}{ext}'
    r=requests.post(sb_storage_url(path),headers=sb_headers({'Content-Type':mime,'x-upsert':'true'}),data=data,timeout=60)
    if r.ok:
        row,err=db_insert('koja_statuses',{'id':str(uuid.uuid4()),'user_id':uid,'text_content':'','media_url':path,'media_type':'video' if mime.startswith('video/') else 'image','visibility':'contacts','expires_at':(datetime.now(timezone.utc)+timedelta(hours=24)).isoformat(),'created_at':utc_now()})
        if err:
            delete_storage_path(path)
    return redirect(url_for('connect_status'))

@app.route('/connect/answer/<call_id>')
@login_required
def connect_answer(call_id):
    uid=current_user()['id']; c=first_row('koja_calls',{'id':call_id})
    if not c or str(c.get('callee_id'))!=str(uid) or c.get('status') not in ('ringing','answered'):
        abort(404)
    return render_page('Answer KOJA Call',r'''<div class="card"><h2>📞 Incoming {{ c.mode|title }} Call</h2><p>From <strong>{{ name }}</strong></p><div id="state">Connecting…</div><div style="display:grid;grid-template-columns:1fr 1fr;gap:10px"><video id="local" autoplay muted playsinline style="width:100%;background:#111;border-radius:10px"></video><video id="remote" autoplay playsinline style="width:100%;background:#111;border-radius:10px"></video></div><button id="hang" class="btn danger">End Call</button></div><script>
const cid={{ call_id|tojson }},mode={{ c.mode|tojson }};
let pc=null,timer=null,iceTimer=null,remoteIce=new Set();
const state=document.getElementById('state');
async function api(u,o){let r=await fetch(u,o);if(!r.ok)throw 0;return r.json();}
async function sendIce(candidate){
  try{await api('/api/connect/call/ice/'+cid,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({candidate})});}catch(e){}
}
async function pullIce(){
  if(!pc||!pc.remoteDescription)return;
  try{
    let x=await api('/api/connect/call/ice/'+cid);
    for(const candidate of (x.candidates||[])){
      const key=JSON.stringify(candidate);
      if(remoteIce.has(key))continue;
      remoteIce.add(key);
      try{await pc.addIceCandidate(candidate);}catch(e){}
    }
  }catch(e){}
}
async function start(){
  try{
    let x=await api('/api/connect/call/check/'+cid);
    if(!x.call.offer)throw 0;
    pc=new RTCPeerConnection({iceServers:[{urls:'stun:stun.l.google.com:19302'}]});
    let st=await navigator.mediaDevices.getUserMedia({audio:true,video:mode==='video'});
    document.getElementById('local').srcObject=st;
    st.getTracks().forEach(t=>pc.addTrack(t,st));
    pc.ontrack=e=>{const st=e.streams[0],v=document.getElementById('remote');v.srcObject=st;v.volume=1;if(window.AudioContext||window.webkitAudioContext){try{const C=window.AudioContext||window.webkitAudioContext,ctx=new C(),src=ctx.createMediaStreamSource(st),gain=ctx.createGain(),dst=ctx.createMediaStreamDestination();gain.gain.value=1.8;src.connect(gain);const boosted=new MediaStream([...st.getVideoTracks(),...dst.stream.getAudioTracks()]);gain.connect(dst);v.srcObject=boosted;v.play().catch(()=>{});}catch(_){} }};
    pc.onicecandidate=e=>{if(e.candidate)sendIce(e.candidate.toJSON?e.candidate.toJSON():e.candidate);};
    pc.onconnectionstatechange=()=>{if(['failed','closed'].includes(pc.connectionState)){state.textContent='Connection failed';}};
    await pc.setRemoteDescription({type:'offer',sdp:x.call.offer});
    await pullIce();
    let ans=await pc.createAnswer();
    await pc.setLocalDescription(ans);
    await api('/api/connect/call/answer/'+cid,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({answer:ans.sdp})});
    state.textContent='Connected';
    iceTimer=setInterval(pullIce,1000);
    timer=setInterval(async()=>{
      try{
        let z=await api('/api/connect/call/check/'+cid);
        if(z.call.status==='ended'){clearInterval(timer);clearInterval(iceTimer);pc.close();state.textContent='Call ended';}
      }catch(e){}
    },1500);
  }catch(e){state.textContent='Could not answer this call.';}
}
document.getElementById('hang').onclick=()=>{fetch('/api/connect/call/end/'+cid,{method:'POST'});clearInterval(timer);clearInterval(iceTimer);if(pc)pc.close();state.textContent='Call ended';};
start();
</script>''',c=c,call_id=call_id,name=_profile_name(c.get('caller_id')))

@app.route('/api/connect/call/ice/<call_id>',methods=['POST','GET'])
@login_required
def connect_call_ice(call_id):
    # Normalize the authenticated user ID before comparing with Supabase UUID values.
    # This prevents valid ICE signaling requests from being rejected with HTTP 403
    # when current_user() returns a UUID-like value instead of a plain string.
    uid=str(current_user()['id'])
    c=first_row('koja_calls',{'id':call_id})
    if not c or uid not in (str(c.get('caller_id')),str(c.get('callee_id'))):
        return jsonify(error='Forbidden'),403

    caller_id=str(c.get('caller_id'))
    callee_id=str(c.get('callee_id'))

    def parse_candidates(value):
        if isinstance(value,list):
            return value
        if isinstance(value,str):
            try:
                parsed=json.loads(value)
                return parsed if isinstance(parsed,list) else []
            except Exception:
                return []
        return []

    caller_ice=parse_candidates(c.get('caller_ice'))
    callee_ice=parse_candidates(c.get('callee_ice'))

    if request.method == 'GET':
        # Return only the other participant's candidates.
        remote=callee_ice if str(uid)==caller_id else caller_ice
        return jsonify(ok=True,candidates=remote)

    d=request.get_json(silent=True) or {}
    candidate=d.get('candidate')
    if not isinstance(candidate,dict):
        return jsonify(error='Invalid ICE candidate'),400

    # Basic size guard for signaling data.
    if len(json.dumps(candidate,separators=(',',':'))) > 12000:
        return jsonify(error='ICE candidate too large'),413

    mine=caller_ice if str(uid)==caller_id else callee_ice
    mine_json=json.dumps(mine,separators=(',',':'),sort_keys=True)
    candidate_json=json.dumps(candidate,separators=(',',':'),sort_keys=True)

    # De-duplicate candidates without changing any other KOJA service.
    if candidate_json not in {
        json.dumps(x,separators=(',',':'),sort_keys=True)
        for x in mine if isinstance(x,dict)
    }:
        mine.append(candidate)

    field='caller_ice' if str(uid)==caller_id else 'callee_ice'
    updated,err=db_update('koja_calls',{'id':call_id},{field:mine})
    if err:
        return jsonify(error=str(err)[:500]),500

    return jsonify(ok=True,count=len(mine))

@app.route('/api/connect/call/answer/<call_id>',methods=['POST'])
@login_required
def connect_call_answer(call_id):
    uid=current_user()['id']; c=first_row('koja_calls',{'id':call_id})
    if not c or str(c.get('callee_id'))!=str(uid):
        return jsonify(error='Forbidden'),403

    d=request.get_json(silent=True) or {}
    answer=clean(d.get('answer'))
    if not answer:
        return jsonify(error='Missing answer'),400

    # Idempotent answer: repeated browser requests must not produce a conflict.
    # Only the authenticated callee may change the answer.
    status=str(c.get('status') or '').lower()
    if status in ('ended','rejected'):
        return jsonify(error='Call is no longer active',status=status),409

    if status == 'answered' and c.get('answer'):
        return jsonify(ok=True,already_answered=True,call=c)

    updated,err=db_update('koja_calls',{'id':call_id},{
        'answer':answer,
        'status':'answered',
        'answered_at':utc_now()
    })
    if err:
        return jsonify(error=str(err)[:500]),500
    return jsonify(ok=True,call=updated or {'id':call_id,'status':'answered'})

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
    return render_page('KOJA Call',r'''<div class="card"><h2>📞 KOJA {{ mode|title }} Call</h2><p>Calling <strong>{{ name }}</strong></p><div id="state">Connecting…</div><div style="display:grid;grid-template-columns:1fr 1fr;gap:10px"><video id="local" autoplay muted playsinline style="width:100%;background:#111;border-radius:10px"></video><video id="remote" autoplay playsinline style="width:100%;background:#111;border-radius:10px"></video></div><button id="hang" class="btn danger">End Call</button></div><script>
const target={{ user_id|tojson }},mode={{ mode|tojson }};
let callId=null,pc=null,timer=null,iceTimer=null,remoteIce=new Set(),started=Date.now();
const state=document.getElementById('state');
const unavailable='This contact is not available because the internet or network connection could not be reached.';
function speak(){if('speechSynthesis'in window){speechSynthesis.cancel();speechSynthesis.speak(new SpeechSynthesisUtterance(unavailable));}}
function fail(msg){state.textContent=msg||unavailable;speak();clearInterval(timer);clearInterval(iceTimer);if(pc)pc.close();}
async function api(u,o){let r=await fetch(u,o);if(!r.ok)throw 0;return r.json();}
async function sendIce(candidate){
  try{await api('/api/connect/call/ice/'+callId,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({candidate})});}catch(e){}
}
async function pullIce(){
  if(!callId||!pc||!pc.remoteDescription)return;
  try{
    let x=await api('/api/connect/call/ice/'+callId);
    for(const candidate of (x.candidates||[])){
      const key=JSON.stringify(candidate);
      if(remoteIce.has(key))continue;
      remoteIce.add(key);
      try{await pc.addIceCandidate(candidate);}catch(e){}
    }
  }catch(e){}
}
async function start(){
  try{
    if(!navigator.onLine)throw 0;
    let c=await api('/api/connect/call/create',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({callee_id:target,mode})});
    callId=c.call.id;
    pc=new RTCPeerConnection({iceServers:[{urls:'stun:stun.l.google.com:19302'}]});
    let st=await navigator.mediaDevices.getUserMedia({audio:true,video:mode==='video'});
    document.getElementById('local').srcObject=st;
    st.getTracks().forEach(t=>pc.addTrack(t,st));
    pc.ontrack=e=>{const st=e.streams[0],v=document.getElementById('remote');v.srcObject=st;v.volume=1;if(window.AudioContext||window.webkitAudioContext){try{const C=window.AudioContext||window.webkitAudioContext,ctx=new C(),src=ctx.createMediaStreamSource(st),gain=ctx.createGain(),dst=ctx.createMediaStreamDestination();gain.gain.value=1.8;src.connect(gain);const boosted=new MediaStream([...st.getVideoTracks(),...dst.stream.getAudioTracks()]);gain.connect(dst);v.srcObject=boosted;v.play().catch(()=>{});}catch(_){} }};
    pc.onicecandidate=e=>{if(e.candidate)sendIce(e.candidate.toJSON?e.candidate.toJSON():e.candidate);};
    pc.onconnectionstatechange=()=>{if(['failed','closed'].includes(pc.connectionState))fail();};
    let offer=await pc.createOffer();
    await pc.setLocalDescription(offer);
    await api('/api/connect/call/offer/'+callId,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({offer:offer.sdp})});
    state.textContent='Ringing…';
    iceTimer=setInterval(pullIce,1000);
    timer=setInterval(async()=>{
      if(Date.now()-started>120000){fail();return;}
      try{
        let x=await api('/api/connect/call/check/'+callId);
        if(x.call.status==='ended'||x.call.status==='rejected'){fail();return;}
        if(x.call.answer&&!pc.currentRemoteDescription){
          await pc.setRemoteDescription({type:'answer',sdp:x.call.answer});
          state.textContent='Connected';
          pullIce();
        }
      }catch(e){fail();}
    },1500);
  }catch(e){fail();}
}
document.getElementById('hang').onclick=()=>{if(callId)fetch('/api/connect/call/end/'+callId,{method:'POST'});clearInterval(timer);clearInterval(iceTimer);if(pc)pc.close();state.textContent='Call ended';};
window.addEventListener('offline',()=>fail());
start();
</script>''',user_id=user_id,mode=mode,name=_profile_name(user_id))

@app.route('/api/connect/call/create',methods=['POST'])
@login_required
def connect_call_create():
    uid=current_user()['id']; d=request.get_json(silent=True) or {}; callee=clean(d.get('callee_id')); mode=d.get('mode','video')
    if callee==uid or not find_user_by_id(callee) or mode not in ('voice','video'):return jsonify(error='Invalid call'),400
    c=_direct_conversation(uid,callee); row,err=db_insert('koja_calls',{'id':str(uuid.uuid4()),'conversation_id':c['id'],'caller_id':uid,'callee_id':callee,'mode':mode,'status':'ringing','created_at':utc_now()})
    if err:return jsonify(error=err),500
    db_insert('koja_notifications',{'user_id':callee,'notification_type':'call','title':f'Incoming {mode} call','body':f'{_profile_name(uid)} is calling you.','related_id':row['id']});return jsonify(call=row)

@app.route('/api/connect/call/offer/<call_id>',methods=['POST'])
@login_required
def connect_call_offer(call_id):
    uid=current_user()['id']; c=first_row('koja_calls',{'id':call_id})
    if not c or str(c.get('caller_id'))!=str(uid):return jsonify(error='Forbidden'),403
    d=request.get_json(silent=True) or {};db_update('koja_calls',{'id':call_id},{'offer':clean(d.get('offer'))});return jsonify(ok=True)

@app.route('/api/connect/call/check/<call_id>')
@login_required
def connect_call_check(call_id):
    uid=str(current_user()['id']);c=first_row('koja_calls',{'id':call_id})
    if not c or uid not in (str(c.get('caller_id')),str(c.get('callee_id'))):return jsonify(error='Forbidden'),403
    return jsonify(call=c)

@app.route('/api/connect/call/end/<call_id>',methods=['POST'])
@login_required
def connect_call_end(call_id):
    uid=str(current_user()['id']);c=first_row('koja_calls',{'id':call_id})
    if not c or uid not in (str(c.get('caller_id')),str(c.get('callee_id'))):return jsonify(error='Forbidden'),403
    db_update('koja_calls',{'id':call_id},{'status':'ended','ended_at':utc_now()});return jsonify(ok=True)

@app.route('/setup/connect-sql')
def connect_sql():
    return '<pre style="white-space:pre-wrap">'+KOJA_CONNECT_SQL.replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')+'</pre>'


# ============================================================
# PROFESSION-SPECIFIC + PUBLIC COMMUNICATION
# ============================================================

def profession_slug(value):
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
# KOJA NEXT-GENERATION EXPERIENCE V48
# AI • COMMUNICATION • MEDIA • NEWS
# ============================================================

NEXTGEN_SQL = r'''
create table if not exists public.koja_news_reactions (
    post_id uuid not null references public.koja_public_posts(id) on delete cascade,
    user_id uuid not null, reaction text not null default 'like',
    created_at timestamptz default now(), primary key(post_id,user_id)
);
create index if not exists koja_news_reactions_post_idx on public.koja_news_reactions(post_id);

create table if not exists public.koja_media_events (
    id uuid primary key default gen_random_uuid(),
    post_id uuid references public.koja_public_posts(id) on delete cascade,
    user_id uuid, session_id text not null, event_type text not null,
    watch_seconds numeric default 0, completion_percent numeric default 0,
    created_at timestamptz default now()
);
create index if not exists koja_media_events_post_idx on public.koja_media_events(post_id,created_at desc);
create index if not exists koja_media_events_session_idx on public.koja_media_events(session_id,created_at desc);

create table if not exists public.koja_ai_feedback (
    id uuid primary key default gen_random_uuid(), user_id uuid,
    rating text, prompt_hash text, created_at timestamptz default now()
);
'''

def _ai_file_extract(filename, raw_bytes):
    """Extract safe, bounded text from an uploaded KOJA AI document."""
    name=secure_filename(filename or "attachment") or "attachment"
    ext=name.rsplit('.',1)[-1].lower() if '.' in name else ''
    if ext in {'txt','md','csv','json','log'}:
        for enc in ('utf-8','utf-8-sig','cp1252','latin-1'):
            try:
                text=raw_bytes.decode(enc)
                break
            except Exception:
                text=''
        return text[:90000], name, ext
    if ext=='pdf':
        if PdfReader is None:
            return '', name, ext
        try:
            reader=PdfReader(io.BytesIO(raw_bytes))
            parts=[]
            for page in reader.pages[:80]:
                try: parts.append(page.extract_text() or '')
                except Exception: pass
            return '\n\n'.join(parts)[:90000], name, ext
        except Exception as exc:
            logger.warning('KOJA AI PDF extraction failed: %s',exc)
            return '', name, ext
    if ext=='docx':
        if DocxDocument is None:
            return '', name, ext
        try:
            doc=DocxDocument(io.BytesIO(raw_bytes))
            parts=[para.text for para in doc.paragraphs if para.text.strip()]
            for table in doc.tables:
                for row in table.rows:
                    parts.append(' | '.join(cell.text.strip() for cell in row.cells))
            return '\n'.join(parts)[:90000], name, ext
        except Exception as exc:
            logger.warning('KOJA AI DOCX extraction failed: %s',exc)
            return '', name, ext
    return '', name, ext

def _ai_needs_web_research(prompt):
    q=clean(prompt).lower()
    if not q: return False
    patterns=(
        r'\bresearch\b', r'\blatest\b', r'\bcurrent\b', r'\btoday\b', r'\btonight\b',
        r'\bthis week\b', r'\bthis month\b', r'\bnews\b', r'\brecent\b', r'\bsource(?:s)?\b',
        r'\bcitation(?:s)?\b', r'\bacademic literature\b', r'\bstudies\b', r'\bevidence\b',
        r'\baccording to\b', r'\bstatistics\b', r'\bdata\b', r'\bwho is the current\b',
        r'\bwhat happened\b', r'\bwhat are the latest\b'
    )
    return any(re.search(x,q) for x in patterns)

def _ai_research_context(query):
    """Collect fresh multi-source evidence for ChatGPT-style automatic research."""
    try:
        results=_research_collect(query)[:8]
    except Exception as exc:
        logger.warning('Automatic AI research collection failed: %s',exc)
        return [], ''
    bundle=[]
    for i,r in enumerate(results,1):
        bundle.append(
            f"[{i}] {clean(r.get('title',''))} | {clean(r.get('source',''))} | {r.get('year') or 'n.d.'}\n"
            f"Evidence: {clean(r.get('snippet',''))[:1400]}\nURL: {clean(r.get('url',''))}"
        )
    return results, '\n\n'.join(bundle)

def _ai_researched_answer(prompt, system, max_output_tokens=2400, timeout=50):
    """Answer with fresh evidence when the user's request clearly needs research."""
    results,bundle=_ai_research_context(prompt)
    if not bundle:
        return _ai_call(prompt,system,max_output_tokens=max_output_tokens,timeout=timeout,preferred_model=None)
    grounded_prompt=(
        f"USER QUESTION:\n{prompt}\n\n"
        "FRESH KOJA RESEARCH EVIDENCE:\n"+bundle+"\n\n"
        "Answer the user's question directly. Use the evidence above where relevant. "
        "Do not invent sources or claim that you browsed pages that are not represented above. "
        "For factual claims supported by the evidence, add compact source markers such as [1] or [2]. "
        "If the evidence is insufficient or conflicting, say so clearly."
    )
    answer,err=_ai_call(grounded_prompt,system+" You have fresh research evidence supplied by KOJA. Be source-aware and never fabricate citations.",max_output_tokens=max_output_tokens,timeout=timeout,preferred_model=None)
    return answer,err


@app.route('/ai-next', methods=['GET'])
@login_required
def ai_nextgen():
    return render_page('KOJA AI', r'''<meta charset="utf-8"><style>
html,body{margin:0!important;padding:0!important}.ng-full{position:fixed;inset:0;width:100vw;height:100dvh;z-index:9999;background:var(--bg,#fff);color:var(--text,#111);display:flex;overflow:hidden}.ng-sidebar{width:280px;flex:0 0 280px;background:var(--surface,#f7f7f8);border-right:1px solid var(--border,#ddd);display:flex;flex-direction:column}.ng-side-close{display:none;width:38px;height:38px;border:0;background:transparent;color:inherit;border-radius:10px;font-size:22px;cursor:pointer}.ng-side-head{display:flex;align-items:center;gap:6px}.ng-side-top{padding:12px;border-bottom:1px solid var(--border,#ddd);position:sticky;top:0;z-index:5;background:var(--surface,#f7f7f8)}.ng-new{width:100%;height:44px;border:1px solid var(--border,#ccc);border-radius:12px;background:var(--surface,#fff);color:inherit;font-weight:600;cursor:pointer}.ng-new:hover,.ng-hitem:hover{background:rgba(127,127,127,.1)}.ng-history-title{padding:14px 14px 7px;font-size:12px;font-weight:700;opacity:.58;text-transform:uppercase;letter-spacing:.06em}.ng-history{flex:1;overflow-y:auto;padding:5px 8px 14px}.ng-hitem{display:block;width:100%;text-align:left;border:0;background:transparent;color:inherit;padding:11px 12px;border-radius:10px;cursor:pointer;margin:2px 0}.ng-hitem strong{display:block;font-size:14px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.ng-empty{padding:18px 10px;text-align:center;opacity:.55;font-size:13px}.ng-main{flex:1;min-width:0;height:100%;display:flex;flex-direction:column;background:var(--bg,#fff)}.ng-topbar{height:58px;flex:0 0 58px;border-bottom:1px solid var(--border,#ddd);display:flex;align-items:center;padding:0 18px;gap:10px;background:var(--bg,#fff)}.ng-brand{display:flex;align-items:center;gap:9px;font-weight:700;font-size:16px}.ng-status{margin-left:auto;font-size:12px;opacity:.58}.ng-top-new{display:none;height:38px;border:1px solid var(--border,#ccc);background:var(--surface,#fff);color:inherit;border-radius:10px;padding:0 10px;font-weight:600;cursor:pointer}.ng-menu{display:none;width:38px;height:38px;border:0;background:transparent;border-radius:10px;font-size:22px;cursor:pointer;color:inherit}.ng-chat{flex:1;min-height:0;overflow-y:auto;overflow-x:hidden;overscroll-behavior-y:contain;scroll-behavior:smooth;padding:28px 18px 150px;scrollbar-gutter:stable;scrollbar-width:thin}.ng-chat::-webkit-scrollbar,.ng-history::-webkit-scrollbar{width:8px}.ng-chat::-webkit-scrollbar-thumb,.ng-history::-webkit-scrollbar-thumb{background:rgba(127,127,127,.35);border-radius:999px}.ng-latest{position:fixed;right:22px;bottom:118px;z-index:8;border:1px solid var(--border,#ccc);background:var(--surface,#fff);color:inherit;border-radius:999px;padding:8px 12px;box-shadow:0 4px 16px rgba(0,0,0,.12);cursor:pointer;font-size:12px;display:none}.ng-latest.show{display:block}.ng-inner{max-width:850px;margin:0 auto}.ng-welcome{text-align:center;padding:12vh 15px 25px}.ng-welcome h1{font-size:30px;margin:0 0 9px}.ng-welcome p{opacity:.6;margin:0}.ng-msg{display:flex;margin:0 auto;padding:22px 0;gap:13px;max-width:850px}.ng-msg.user{justify-content:flex-end}.ng-avatar{width:30px;height:30px;flex:0 0 30px;border-radius:9px;display:grid;place-items:center;font-size:13px;font-weight:700}.ng-msg.assistant .ng-avatar{background:linear-gradient(135deg,#176b87,#19a7b8);color:#fff}.ng-msg.user .ng-avatar{background:#ececec;color:#333;order:2}.ng-content{max-width:760px;line-height:1.65;font-size:15px;overflow-wrap:anywhere}.ng-content p{margin:0 0 14px}.ng-content p:last-child{margin-bottom:0}.ng-content strong{font-weight:700}.ng-msg.user .ng-content{background:#f1f1f1;padding:11px 15px;border-radius:18px;line-height:1.5}.ng-composer-wrap{position:absolute;left:280px;right:0;bottom:0;padding:12px 18px 18px;background:linear-gradient(transparent,var(--bg,#fff) 30%)}.ng-attachment{max-width:850px;margin:0 auto 7px;display:none;align-items:center;gap:8px;padding:7px 10px;border:1px solid var(--border,#ddd);border-radius:12px;background:var(--surface,#fff);font-size:12px}.ng-attachment.show{display:flex}.ng-attachment-name{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1}.ng-attachment-clear{border:0;background:transparent;color:inherit;cursor:pointer;font-size:16px}.ng-composer{max-width:850px;margin:0 auto;border:1px solid #cfcfcf;border-radius:20px;background:var(--surface,#fff);box-shadow:0 3px 18px rgba(0,0,0,.08);display:flex;align-items:flex-end;padding:8px 9px 8px 10px;gap:8px}.ng-composer textarea{flex:1;border:0!important;outline:0!important;box-shadow:none!important;background:transparent!important;color:inherit!important;margin:0!important;padding:8px 0!important;min-height:28px;max-height:180px;resize:none;font:inherit;line-height:1.45}.ng-attach{width:40px;height:40px;flex:0 0 40px;border:0;border-radius:12px;background:transparent;color:inherit;cursor:pointer;font-size:19px}.ng-send{width:40px;height:40px;flex:0 0 40px;border:0;border-radius:12px;background:#176b87;color:#fff;cursor:pointer;font-size:17px}.ng-send:disabled{opacity:.45;cursor:not-allowed}.ng-hint{text-align:center;font-size:11px;opacity:.45;margin-top:7px}.ng-private{font-size:11px;opacity:.62;text-align:center;margin:2px auto 8px;max-width:850px}.ng-private strong{opacity:.9}.ng-koja-logo{width:30px;height:30px;border-radius:9px;display:inline-grid;place-items:center;background:linear-gradient(135deg,#19a7b8,#f2b84b);box-shadow:0 4px 14px rgba(0,0,0,.18);flex:0 0 30px}.ng-koja-logo svg{width:21px;height:21px}.ng-side-note{font-size:11px;line-height:1.45;opacity:.6;padding:8px 10px;border:1px solid var(--border,#ddd);border-radius:10px;margin:8px 10px}@media(max-width:800px){.ng-sidebar{position:absolute;left:0;top:0;bottom:0;z-index:20;transform:translateX(-100%);transition:transform .2s ease;box-shadow:8px 0 30px rgba(0,0,0,.12)}.ng-sidebar.open{transform:translateX(0)}.ng-menu{display:block}.ng-top-new{display:inline-flex;align-items:center;justify-content:center}.ng-side-close{display:block}.ng-composer-wrap{left:0;padding:10px 10px 12px}.ng-chat{padding:18px 12px 125px}.ng-msg{padding:17px 3px}.ng-content{font-size:14px}.ng-welcome{padding-top:13vh}.ng-welcome h1{font-size:26px}}
</style><div class="ng-full"><aside id="ngSidebar" class="ng-sidebar"><div class="ng-side-top"><div class="ng-side-head"><button id="newChat" class="ng-new">＋ New chat</button><button id="closeMenu" class="ng-side-close" aria-label="Close chat history">×</button></div></div><div class="ng-history-title">History</div><div class="ng-side-note">🔒 Private to your signed-in KOJA account. Chats are not public. Older chats remain saved unless deleted.</div><div id="historyList" class="ng-history"><div class="ng-empty">Loading history…</div></div></aside><main class="ng-main"><header class="ng-topbar"><button id="menuBtn" class="ng-menu" aria-label="Open chat history">☰</button><div class="ng-brand"><span class="ng-koja-logo" aria-label="KOJA logo"><svg viewBox="0 0 24 24" fill="none"><path d="M5 18V6h7.2a5.3 5.3 0 0 1 0 10.6H8.5" stroke="white" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/><path d="M8.5 9.1h3.4a1.9 1.9 0 0 1 0 3.8H8.5" stroke="white" stroke-width="2.2" stroke-linecap="round"/></svg></span><span>KOJA AI</span></div><span id="aiState" class="ng-status">Ready</span><button id="topNewChat" class="ng-top-new" type="button">＋ New</button></header><section id="aiChat" class="ng-chat"><div class="ng-inner"></div></section><button id="latestBtn" class="ng-latest" type="button">↓ Latest</button><div class="ng-composer-wrap"><div id="attachment" class="ng-attachment"><span>📎</span><span id="attachmentName" class="ng-attachment-name"></span><button id="clearAttachment" class="ng-attachment-clear" type="button" aria-label="Remove attachment">×</button></div><div class="ng-composer"><label class="ng-attach" title="Attach a file" aria-label="Attach a file">📎<input id="fileInput" type="file" accept=".pdf,.docx,.txt,.md,.csv,.json" hidden></label><textarea id="aiPrompt" placeholder="Message KOJA AI…" maxlength="12000" rows="1" aria-label="Message KOJA AI"></textarea><button id="aiSend" class="ng-send" type="button" aria-label="Send">➤</button></div><div class="ng-private"><strong>🔒 Private history</strong> — your KOJA AI chats are tied to your signed-in account and are not public.</div><div class="ng-hint">KOJA AI can make mistakes. Check important information.</div></div></main></div><script>
const ac=document.getElementById('aiChat'),inner=ac.querySelector('.ng-inner'),ap=document.getElementById('aiPrompt'),as=document.getElementById('aiState'),send=document.getElementById('aiSend'),hl=document.getElementById('historyList'),sidebar=document.getElementById('ngSidebar'),fileInput=document.getElementById('fileInput'),attachment=document.getElementById('attachment'),attachmentName=document.getElementById('attachmentName');let hist=[],conversationId=null,attachedContext='',attachedName='';
function esc(x){return String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function cleanUtf8(x){let s=String(x??'');if(!/[âÂÃð]/.test(s))return s;try{return decodeURIComponent(escape(s));}catch(_){return s;}}
function scrollLatest(behavior='auto'){requestAnimationFrame(()=>ac.scrollTo({top:ac.scrollHeight,behavior}));}
function renderAIText(v){v=cleanUtf8(String(v??'')).replace(/\r\n?/g,'\n');let parts=v.split(/\n{2,}/).map(x=>x.trim()).filter(Boolean);if(!parts.length)return '';return parts.map(part=>{let x=esc(part);x=x.replace(/\*\*(.+?)\*\*/gs,'<strong>$1</strong>');x=x.replace(/(^|\n)\* (.+)/g,'$1• $2');x=x.replace(/(^|\n)(\d+)\. (.+)/g,'$1$2. $3');return '<p>'+x.replace(/\n/g,'<br>')+'</p>'}).join('')}function redraw(forceLatest=false){const oldHeight=ac.scrollHeight,oldTop=ac.scrollTop,wasNearBottom=oldHeight-oldTop-ac.clientHeight<120;inner.innerHTML='';if(!hist.length){inner.innerHTML='<div class="ng-welcome"><h1>How can I help you today?</h1><p>Ask KOJA AI anything.</p></div>';updateLatestButton();return}hist.forEach(m=>{let d=document.createElement('div');d.className='ng-msg '+(m.role==='user'?'user':'assistant');let a=document.createElement('div');a.className='ng-avatar';a.textContent=m.role==='user'?'U':'✦';let c=document.createElement('div');c.className='ng-content';c.innerHTML=renderAIText(m.content);d.appendChild(a);d.appendChild(c);inner.appendChild(d)});if(forceLatest||wasNearBottom||hist.length<=1)scrollLatest();else requestAnimationFrame(()=>{const delta=ac.scrollHeight-oldHeight;ac.scrollTop=oldTop+delta;updateLatestButton()});updateLatestButton()}
function resizeBox(){ap.style.height='auto';ap.style.height=Math.min(ap.scrollHeight,180)+'px'}
async function loadHistory(){try{let r=await fetch('/api/nextgen/ai/history',{cache:'no-store'}),d=await r.json();hl.innerHTML='';if(!d.chats?.length){hl.innerHTML='<div class="ng-empty">No previous chats yet.</div>';return}let seen=new Set();d.chats.forEach(c=>{let title=cleanUtf8(c.title||'KOJA AI chat').trim()||'KOJA AI chat';let key=title.toLowerCase().replace(/\s+/g,' ');if(seen.has(key))return;seen.add(key);let b=document.createElement('button');b.className='ng-hitem';let archived=c.is_archived?'<span style="font-size:10px;opacity:.55;margin-left:6px">Archived</span>':'';b.innerHTML='<strong>'+esc(title)+archived+'</strong>';b.onclick=()=>openChat(c.id);hl.appendChild(b)})}catch(e){hl.innerHTML='<div class="ng-empty">History unavailable.</div>'}}
async function openChat(id){let r=await fetch('/api/nextgen/ai/history/'+encodeURIComponent(id),{cache:'no-store'}),d=await r.json();if(!r.ok){as.textContent='Unavailable';return}conversationId=id;hist=d.messages||[];attachedContext='';attachedName='';attachment.classList.remove('show');redraw(true);as.textContent='Ready';sidebar.classList.remove('open');ap.focus()}
function newChat(){conversationId=null;hist=[];attachedContext='';attachedName='';fileInput.value='';attachment.classList.remove('show');ap.value='';resizeBox();as.textContent='Ready';redraw(true);ap.focus();sidebar.classList.remove('open');window.scrollTo(0,0)}
async function uploadFile(file){if(!file)return;as.textContent='Reading file…';let fd=new FormData();fd.append('file',file);try{let r=await fetch('/api/nextgen/ai/file',{method:'POST',body:fd});let d=await r.json();if(!r.ok)throw Error(d.error||'File could not be read');attachedContext=d.text||'';attachedName=d.name||file.name;attachmentName.textContent=attachedName+(d.characters?' · '+d.characters.toLocaleString()+' chars':'');attachment.classList.add('show');as.textContent='Ready';ap.focus()}catch(e){as.textContent='Unavailable';alert(e.message)}}
async function ask(){let q=ap.value.trim();if(!q||send.disabled)return;let fileCtx=attachedContext,fileName=attachedName;attachedContext='';attachedName='';fileInput.value='';attachment.classList.remove('show');ap.value='';resizeBox();hist.push({role:'user',content:q},{role:'assistant',content:''});redraw(true);send.disabled=true;as.textContent='Generating…';try{let r=await fetch('/api/nextgen/ai/stream',{method:'POST',headers:{'Content-Type':'application/json','Accept':'text/event-stream'},body:JSON.stringify({prompt:q,history:hist.slice(-12),conversation_id:conversationId,file_context:fileCtx,file_name:fileName})});if(!r.ok){let d=await r.json().catch(()=>({}));throw Error(d.error||'KOJA AI is unavailable')}let reader=r.body.getReader(),dec=new TextDecoder(),buf='';while(true){let z=await reader.read();if(z.done)break;buf+=dec.decode(z.value,{stream:true});let es=buf.split('\n\n');buf=es.pop()||'';for(let ev of es){let line=ev.split('\n').find(x=>x.startsWith('data:'));if(!line)continue;let x;try{x=JSON.parse(line.slice(5).trim())}catch(_){continue}if(x.type==='conversation')conversationId=x.id;else if(x.type==='token'){hist[hist.length-1].content+=x.text||'';redraw()}else if(x.type==='error')throw Error(x.message||'KOJA AI unavailable')}}as.textContent='Ready';loadHistory()}catch(e){if(hist.at(-1)?.role==='assistant')hist[hist.length-1].content=e.message;as.textContent='Unavailable';redraw()}finally{send.disabled=false;ap.focus()}}
const latestBtn=document.getElementById('latestBtn');function updateLatestButton(){const away=ac.scrollHeight-ac.scrollTop-ac.clientHeight>180;latestBtn.classList.toggle('show',away)}latestBtn.onclick=()=>scrollLatest('smooth');ac.addEventListener('scroll',updateLatestButton,{passive:true});document.getElementById('topNewChat').onclick=newChat;send.onclick=ask;document.getElementById('newChat').onclick=newChat;document.getElementById('menuBtn').onclick=()=>sidebar.classList.toggle('open');document.getElementById('closeMenu').onclick=()=>sidebar.classList.remove('open');document.getElementById('clearAttachment').onclick=()=>{attachedContext='';attachedName='';fileInput.value='';attachment.classList.remove('show');as.textContent='Ready';ap.focus()};fileInput.onchange=()=>uploadFile(fileInput.files&&fileInput.files[0]);ap.addEventListener('input',resizeBox);ap.addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();ask()}});redraw();loadHistory();</script>''')

@app.route('/api/nextgen/ai/history', methods=['GET'])
@login_required
def api_nextgen_ai_history():
    uid=str((current_user() or {}).get('id') or '')
    chats=db_select('koja_ai_conversations', {'user_id':uid}, order='updated_at.desc', limit=200)
    out=[]
    for c in chats:
        msgs=db_select('koja_ai_messages', {'conversation_id':c.get('id'),'user_id':uid}, order='created_at.desc', limit=5)
        preview=next((clean(m.get('content'))[:100] for m in msgs if m.get('role')=='user'),'')
        out.append({'id':c.get('id'),'title':c.get('title') or 'KOJA AI chat','preview':preview,'updated_at':c.get('updated_at'),'is_archived':bool(c.get('is_archived'))})
    resp=jsonify(chats=out)
    resp.headers['Cache-Control']='private, no-store, max-age=0'
    resp.headers['X-Robots-Tag']='noindex, nofollow, noarchive'
    return resp

@app.route('/api/nextgen/ai/history/<conversation_id>', methods=['GET'])
@login_required
def api_nextgen_ai_history_chat(conversation_id):
    uid=str((current_user() or {}).get('id') or '')
    owned=db_select('koja_ai_conversations', {'id':conversation_id,'user_id':uid}, limit=1)
    if not owned:return jsonify(error='Chat not found.'),404
    msgs=db_select('koja_ai_messages', {'conversation_id':conversation_id,'user_id':uid}, order='created_at.asc', limit=1000)
    resp=jsonify(id=conversation_id,title=owned[0].get('title') or 'KOJA AI chat',messages=[{'role':m.get('role'),'content':m.get('content') or ''} for m in msgs])
    resp.headers['Cache-Control']='private, no-store, max-age=0'
    resp.headers['X-Robots-Tag']='noindex, nofollow, noarchive'
    return resp

def api_nextgen_ai_models():
    groq,gemini,openai=_ai_model_candidates()
    return jsonify({
        "groq":groq if os.getenv("GROQ_API_KEY") else [],
        "gemini":gemini if os.getenv("GEMINI_API_KEY") else [],
        "openai":openai if os.getenv("OPENAI_API_KEY") else [],
        "default":(groq[0] if os.getenv("GROQ_API_KEY") and groq else (openai[0] if os.getenv("OPENAI_API_KEY") and openai else (gemini[0] if gemini else None))),
    })

@app.route('/api/nextgen/ai/file', methods=['POST'])
@login_required
def api_nextgen_ai_file():
    f=request.files.get('file')
    if not f or not f.filename:
        return jsonify(error='Choose a file first.'),400
    if _rate_limited('next-ai-file:'+str((current_user() or {}).get('id') or request.remote_addr),20,300):
        return jsonify(error='Too many file uploads. Please wait.'),429
    name=secure_filename(f.filename) or 'attachment'
    ext=name.rsplit('.',1)[-1].lower() if '.' in name else ''
    if ext not in {'pdf','docx','txt','md','csv','json'}:
        return jsonify(error='KOJA AI currently reads PDF, Word (.docx), TXT, Markdown, CSV and JSON files.'),400
    raw=f.read()
    if not raw:return jsonify(error='The uploaded file is empty.'),400
    if len(raw)>15*1024*1024:return jsonify(error='File is too large. Maximum 15 MB.'),413
    text,clean_name,_=_ai_file_extract(name,raw)
    if not text.strip():
        return jsonify(error='KOJA AI could not extract readable text from this file.'),422
    return jsonify(ok=True,name=clean_name,characters=len(text),text=text)

@app.route('/api/nextgen/ai/stream', methods=['POST'])
@login_required
def api_nextgen_ai_stream():
    d=request.get_json(silent=True) or {}; prompt=clean(d.get('prompt'))
    if not prompt:return jsonify(error='Enter a message.'),400
    uid=(current_user() or {}).get('id')
    if len(prompt)>12000:return jsonify(error='Message is too long. Maximum 12,000 characters.'),400
    if _rate_limited('next-ai:'+str(uid or request.remote_addr),20,300):return jsonify(error='Too many requests. Please wait.'),429
    hist=d.get('history') or []; conversation_id=clean(d.get('conversation_id'))
    owned=db_select('koja_ai_conversations',{'id':conversation_id,'user_id':uid},limit=1) if conversation_id else []
    if not owned:
        row,err=db_insert('koja_ai_conversations',{'user_id':uid,'title':prompt[:80] or 'KOJA AI chat'})
        if not row or not row.get('id'):return jsonify(error='KOJA AI history storage is not ready.'),500
        conversation_id=row['id']
    context='\n'.join(f"{x.get('role','user')}: {str(x.get('content',''))[:3500]}" for x in hist[-8:] if isinstance(x,dict))
    file_context=clean(d.get('file_context'))[:90000]
    file_name=clean(d.get('file_name'))[:180]
    system=('You are KOJA AI, an intelligent general-purpose assistant inside KOJA AFRICA. Be accurate, useful, natural and conversational like a modern ChatGPT-style assistant. '
            'Answer directly, explain clearly, help with writing, learning, coding, planning, analysis and everyday tasks. Never invent facts, sources, capabilities or actions. '
            'When fresh evidence is supplied by KOJA, use it carefully and cite it with compact [n] markers. If the user attached a file, treat its contents as user-provided context and answer questions about it faithfully.')
    base_prompt=(('Conversation context:\n'+context+'\n\n') if context else '')
    if file_context:
        base_prompt+=f"ATTACHED FILE ({file_name or 'document'}):\n{file_context}\n\n"
        base_prompt+='Use the attached file as primary context when the question concerns it. If the file does not contain the answer, say so rather than inventing it.\n\n'
    full_prompt=base_prompt+'USER: '+prompt
    wants_research=_ai_needs_web_research(prompt) and not file_context
    def events():
        parts=[];yield ': KOJA AI stream connected\n\n';yield 'data: '+json.dumps({'type':'conversation','id':conversation_id},separators=(',',':'))+'\n\n'
        if wants_research:
            answer,err=_ai_researched_answer(full_prompt,system,max_output_tokens=2400,timeout=55)
            if not answer:
                yield 'data: '+json.dumps({'type':'error','message':_ai_error_message(err)},separators=(',',':'))+'\n\n';return
            # Stream researched answers in small chunks so the UI behaves like normal chat.
            for i in range(0,len(answer),120):
                token=answer[i:i+120];parts.append(token);yield 'data: '+json.dumps({'type':'token','text':token},separators=(',',':'))+'\n\n'
        else:
            for item in _ai_stream(full_prompt,system,max_output_tokens=2400,timeout=90,preferred_model=None):
                if item.get('type')=='token':parts.append(item.get('text') or '');yield 'data: '+json.dumps(item,separators=(',',':'))+'\n\n'
                elif item.get('type')=='error':yield 'data: '+json.dumps({'type':'error','message':_ai_error_message(item.get('error'))},separators=(',',':'))+'\n\n';return
                elif item.get('type')=='done':break
        answer=''.join(parts).strip() or 'No answer returned.'
        db_insert('koja_ai_messages',{'conversation_id':conversation_id,'user_id':uid,'role':'user','content':prompt})
        db_insert('koja_ai_messages',{'conversation_id':conversation_id,'user_id':uid,'role':'assistant','content':answer})
        db_update('koja_ai_conversations',{'id':conversation_id,'user_id':uid},{'updated_at':utc_now(),'title':prompt[:80] or 'KOJA AI chat'})
        yield 'data: '+json.dumps({'type':'done'},separators=(',',':'))+'\n\n';log_activity('ai_chat','User used next-generation KOJA AI.')
    return Response(stream_with_context(events()),mimetype='text/event-stream',headers={'Cache-Control':'no-cache, no-transform','X-Accel-Buffering':'no','Connection':'keep-alive'})

@app.route('/api/nextgen/ai', methods=['POST'])
@login_required
def api_nextgen_ai():
    d=request.get_json(silent=True) or {};prompt=clean(d.get('prompt'))
    if not prompt:return jsonify(error='Enter a message.'),400
    uid=(current_user() or {}).get('id')
    if len(prompt)>12000:return jsonify(error='Message is too long. Maximum 12,000 characters.'),400
    if _rate_limited('next-ai:'+str(uid or request.remote_addr),20,300):return jsonify(error='Too many requests. Please wait.'),429
    hist=d.get('history') or []
    context='\n'.join(f"{x.get('role','user')}: {str(x.get('content',''))[:5000]}" for x in hist[-10:] if isinstance(x,dict))
    file_context=clean(d.get('file_context'))[:90000];file_name=clean(d.get('file_name'))[:180]
    system=('You are KOJA AI, a general-purpose assistant inside KOJA AFRICA. Be accurate, useful, natural and conversational like ChatGPT. '
            'Help with writing, learning, coding, planning, analysis and everyday tasks. Never fabricate facts or sources. If fresh research evidence is supplied, use it carefully.')
    prompt2=(('Conversation context:\n'+context+'\n\n') if context else '')
    if file_context:prompt2+=f"ATTACHED FILE ({file_name or 'document'}):\n{file_context}\n\n"
    prompt2+='USER: '+prompt
    answer,err=(_ai_researched_answer(prompt2,system,2400,55) if _ai_needs_web_research(prompt) and not file_context else _ai_call(prompt2,system,max_output_tokens=2400,timeout=50,preferred_model=None))
    if not answer:return jsonify(error=_ai_error_message(err)),502
    log_activity('ai_chat','User used next-generation KOJA AI.')
    return jsonify(answer=answer)

@app.route('/communication-next')
@login_required
def communication_nextgen():
    uid=current_user()['id']; members=db_select('koja_conversation_members',filters={'user_id':uid},limit=100); chats=[]
    for m in members:
        c=first_row('koja_conversations',{'id':m.get('conversation_id')})
        if not c: continue
        ms=db_select('koja_conversation_members',filters={'conversation_id':c['id']},limit=20)
        other=next((x for x in ms if str(x.get('user_id'))!=str(uid)),None)
        name=_profile_name(other.get('user_id')) if other else (c.get('name') or 'KOJA Group')
        last=db_select('koja_messages',filters={'conversation_id':c['id']},order='created_at.desc',limit=1)
        chats.append({'id':c['id'],'name':name,'last':(last[0].get('body') if last else 'Start a conversation') or 'Media message'})
    return render_page('KOJA Communication',r'''
<style>.comm-wrap{display:grid;grid-template-columns:340px 1fr;gap:16px}.comm-list,.comm-main{background:var(--surface);border:1px solid var(--border);border-radius:20px;overflow:hidden}.comm-search{padding:14px;border-bottom:1px solid var(--border)}.comm-search input{margin:0}.comm-item{display:block;padding:15px;border-bottom:1px solid var(--border);text-decoration:none;color:inherit}.comm-item:hover{background:rgba(127,127,127,.08)}.comm-main{min-height:520px;padding:25px}.comm-orbs{display:flex;gap:12px;flex-wrap:wrap}.comm-orb{width:62px;height:62px;border-radius:20px;background:rgba(23,107,135,.12);display:grid;place-items:center;font-size:25px}.comm-actions{display:grid;grid-template-columns:repeat(2,1fr);gap:10px;margin-top:20px}@media(max-width:800px){.comm-wrap{grid-template-columns:1fr}.comm-main{min-height:300px}}
</style>
<div class="hero"><h2>💬 KOJA Communication</h2><p>One communication layer for messaging, media, voice, video, groups and status.</p></div>
<div class="comm-wrap"><div class="comm-list"><div class="comm-search"><input id="chatSearch" placeholder="Search conversations…"></div><div id="chatList">{% for c in chats %}<a class="comm-item" data-name="{{ c.name|lower }}" href="{{ url_for('connect_chat',conversation_id=c.id) }}"><strong>{{ c.name }}</strong><div class="small">{{ c.last[:100] }}</div></a>{% else %}<div class="comm-item">No conversations yet.</div>{% endfor %}</div></div>
<div class="comm-main"><div class="comm-orbs"><div class="comm-orb">💬</div><div class="comm-orb">🎙️</div><div class="comm-orb">📹</div><div class="comm-orb">👥</div><div class="comm-orb">📎</div></div><h2>Communication, redesigned</h2><p>Continue conversations without leaving KOJA. Open any chat for the existing secure messaging and calling system.</p><div class="comm-actions"><a class="btn" href="{{ url_for('connect_people') }}">👥 Find People</a><a class="btn" href="{{ url_for('connect_group_new') }}">➕ New Group</a><a class="btn secondary" href="{{ url_for('connect_status') }}">🟢 Status</a><a class="btn secondary" href="{{ url_for('connect_calls') }}">📞 Call History</a></div></div></div>
<script>const cs=document.getElementById('chatSearch');cs.oninput=()=>{let q=cs.value.toLowerCase();document.querySelectorAll('.comm-item[data-name]').forEach(x=>x.style.display=x.dataset.name.includes(q)?'block':'none')}</script>
''',chats=chats)

@app.route('/videos')
def public_videos():
    rows=db_select('koja_public_posts',{'is_published':'eq.true'},order='created_at.desc',limit=100) or []
    items=[]
    for p in rows:
        if not p.get('media_url'): continue
        mt=(p.get('media_type') or '').lower()
        if mt!='video':
            path=str(p.get('media_url') or '').lower()
            if path.endswith(('.mp4','.webm','.mov')): mt='video'
        if mt=='video': items.append(p)
    return render_page('KOJA Videos',r'''<style>.videos-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:18px}.video-card{background:var(--surface);border:1px solid var(--border);border-radius:18px;padding:12px}.video-card video{display:block;width:100%;aspect-ratio:16/9;object-fit:contain;background:#000;border-radius:12px}.video-card h3{margin:10px 0 6px}.video-card p{white-space:pre-wrap}.empty{padding:60px 20px;text-align:center}</style><div class="hero"><h2>🎥 KOJA Videos</h2><p>Public videos are visible to everyone. Tap play to watch.</p></div><div class="videos-grid">{% for p in items %}<article class="video-card"><video controls playsinline preload="metadata"><source src="{{ url_for('public_feed_media',post_id=p.id) }}"></video>{% if p.title %}<h3>{{ p.title }}</h3>{% endif %}<p>{{ p.body }}</p><div class="small">{{ p.created_at }}</div></article>{% else %}<div class="card empty"><h2>No public videos yet</h2><p>Published KOJA videos will appear here.</p></div>{% endfor %}</div>''',items=items)

@app.route('/media-next')
def media_nextgen():
    rows=db_select('koja_public_posts',{'is_published':'eq.true'},order='created_at.desc',limit=100) or []
    items=[]
    for p in rows:
        if not p.get('media_url'): continue
        items.append(p)
    return render_page('KOJA Media',r'''
<style>.media-feed{height:calc(100vh - 150px);min-height:540px;overflow-y:auto;scroll-snap-type:y mandatory;background:#05070a;border-radius:22px}.media-card{height:100%;min-height:540px;position:relative;scroll-snap-align:start;display:grid;place-items:center;background:#05070a}.media-card img,.media-card video{width:100%;height:100%;object-fit:contain;max-height:calc(100vh - 150px)}.media-overlay{position:absolute;left:18px;right:18px;bottom:18px;color:#fff;text-shadow:0 2px 8px #000;z-index:2}.media-actions{position:absolute;right:16px;bottom:110px;display:flex;flex-direction:column;gap:9px;z-index:3}.media-actions button{width:50px;height:50px;border-radius:50%;padding:0;margin:0;background:rgba(0,0,0,.55);border:1px solid rgba(255,255,255,.2)}.media-empty{padding:70px;text-align:center;color:#fff}
</style>
<div class="hero"><h2>◉ KOJA Media</h2><p>Immersive media discovery with adaptive interaction, sharing and watch analytics.</p></div>
<div class="media-feed" id="mediaFeed">{% for p in items %}<article class="media-card" data-id="{{ p.id }}" data-seen="0">{% if p.media_type=='video' %}<video src="{{ url_for('public_feed_media',post_id=p.id) }}" playsinline muted loop preload="metadata"></video>{% else %}<img src="{{ url_for('public_feed_media',post_id=p.id) }}" loading="lazy" alt="KOJA media">{% endif %}<div class="media-actions"><button onclick="likeMedia('{{ p.id }}')">♡</button><button onclick="shareMedia('{{ p.id }}')">↗</button><button onclick="copyMedia('{{ p.id }}')">⧉</button></div><div class="media-overlay"><strong>{{ p.title or 'KOJA Media' }}</strong><div>{{ p.body[:220] }}</div><div class="small" style="color:#ddd">{{ p.post_type|title }} · {{ p.created_at }}</div></div></article>{% else %}<div class="media-empty"><h2>No media yet</h2><p>Publish a photo or video to start the KOJA media experience.</p></div>{% endfor %}</div>
<script>
const feed=document.getElementById('mediaFeed');const io=new IntersectionObserver(es=>es.forEach(e=>{let v=e.target.querySelector('video');if(e.isIntersecting){if(v)v.play().catch(()=>{});if(e.target.dataset.seen==='0'){e.target.dataset.seen='1';track(e.target.dataset.id,'impression',0,0)}}else if(v)v.pause()}),{root:feed,threshold:.65});document.querySelectorAll('.media-card').forEach(x=>io.observe(x));
function track(id,type,w,c){fetch('/api/nextgen/media-event',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({post_id:id,event_type:type,watch_seconds:w,completion_percent:c})}).catch(()=>{})}
async function likeMedia(id){await fetch('/public/like/'+id,{method:'POST'});}
function shareMedia(id){let u=location.origin+'/public#post-'+id;if(navigator.share)navigator.share({title:'KOJA Media',url:u});else navigator.clipboard?.writeText(u)}
function copyMedia(id){let u=location.origin+'/public#post-'+id;navigator.clipboard?.writeText(u);}
</script>
''',items=items)

@app.route('/api/nextgen/media-event',methods=['POST'])
def nextgen_media_event():
    d=request.get_json(silent=True) or {}; pid=clean(d.get('post_id')); et=clean(d.get('event_type'))
    allowed={'impression','play','pause','25_percent','50_percent','75_percent','complete','share'}
    if not pid or et not in allowed:return jsonify(error='Invalid event'),400
    sid=request.cookies.get('koja_media_session') or uuid.uuid4().hex
    uid=(current_user() or {}).get('id')
    db_insert('koja_media_events',{'post_id':pid,'user_id':uid,'session_id':sid,'event_type':et,'watch_seconds':float(d.get('watch_seconds') or 0),'completion_percent':float(d.get('completion_percent') or 0),'created_at':utc_now()})
    resp=jsonify(ok=True);resp.set_cookie('koja_media_session',sid,max_age=60*60*24*30,httponly=True,samesite='Lax');return resp

@app.route('/news-next')
def news_nextgen():
    rows=db_select('koja_public_posts',{'is_published':'eq.true','post_type':'eq.news'},order='created_at.desc',limit=100) or []
    for p in rows:
        a=first_row('profiles',{'id':p.get('author_id')}) or {};p['author_name']=a.get('full_name') or a.get('name') or 'KOJA News'
    return render_page('KOJA News',r'''
<style>.news-grid{display:grid;grid-template-columns:minmax(0,1fr) 340px;gap:18px}.news-card{background:var(--surface);border:1px solid var(--border);border-radius:20px;padding:20px;margin-bottom:14px}.news-card img{width:100%;max-height:460px;object-fit:cover;border-radius:15px;margin-top:12px}.news-meta{color:var(--muted);font-size:13px}.news-side{position:sticky;top:85px;height:max-content}.topic{display:inline-block;padding:8px 11px;border:1px solid var(--border);border-radius:999px;margin:4px;text-decoration:none;color:inherit}@media(max-width:800px){.news-grid{grid-template-columns:1fr}.news-side{position:static}}
</style>
<div class="hero"><h2>📰 KOJA News</h2><p>Fast, structured and mobile-first news discovery from KOJA.</p></div><div class="news-grid"><main>{% for p in posts %}<article class="news-card"><div class="news-meta">{{ p.author_name }} · {{ p.created_at }}</div><h2>{{ p.title or 'KOJA News Update' }}</h2><p style="white-space:pre-wrap;line-height:1.75">{{ p.body }}</p>{% if p.media_url %}<img src="{{ url_for('public_feed_media',post_id=p.id) }}" alt="{{ p.title or 'KOJA news' }}" loading="lazy">{% endif %}<div class="actions" style="margin-top:14px"><a class="btn secondary" href="{{ url_for('public_feed') }}#post-{{ p.id }}">💬 Discuss</a><button class="btn secondary" onclick="navigator.clipboard&&navigator.clipboard.writeText(location.origin+'/public#post-{{ p.id }}')">Copy Link</button></div></article>{% else %}<div class="news-card"><h3>No news published yet.</h3><p>KOJA news will appear here as publishers post verified updates.</p></div>{% endfor %}</main><aside class="news-side"><div class="news-card"><h3>KOJA Newsroom</h3><p class="small">News, announcements and important public updates in one place.</p><a class="btn" href="{{ url_for('public_feed') }}">Open Public Feed</a></div><div class="news-card"><h3>Explore</h3><a class="topic" href="{{ url_for('research') }}">Research</a><a class="topic" href="{{ url_for('media_nextgen') }}">Media</a><a class="topic" href="{{ url_for('ai_nextgen') }}">AI</a></div></aside></div>
''',posts=rows)



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
    response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
    response.headers.setdefault("X-Permitted-Cross-Domain-Policies", "none")
    response.headers.setdefault("Origin-Agent-Cluster", "?1")
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
    return {"APP_NAME":APP_NAME,"APP_TAGLINE":APP_TAGLINE,"SITE_URL":SITE_URL,"profession_slug":profession_slug,"csrf_token":csrf_token}

# ============================================================
# KOJA MARKET V3 + KOJA BUSINESS
# ============================================================
KOJA_MARKET_VERSION = '2026.09.08-V6-FULL-BUY-SELL-UI'
KOJA_PLATFORM_FEE_RATE = float(os.getenv('KOJA_PLATFORM_FEE_RATE','0.015'))
KOJA_SELLER_PLANS = {'free':0.0,'pro':99.0,'business':299.0}
KOJA_BUSINESS_PLANS = {'starter':99.0,'growth':299.0,'pro':699.0}

@app.route('/market/checkout', methods=['GET','POST'])
@login_required
def market_cart_checkout():
    uid=(current_user() or {}).get('id')
    carts=db_select('koja_market_cart',{'user_id':uid},limit=100) or []
    ids=[str(x.get('product_id')) for x in carts if x.get('product_id')]
    ps=db_select('koja_market_products',{'id':'in.('+','.join(ids)+')'} if ids else {},limit=200) or []
    pm={str(x.get('id')):x for x in ps}; items=[]; subtotal=0; delivery=0
    for c in carts:
        p=pm.get(str(c.get('product_id')))
        if not p or not as_bool(p.get('is_published')) or str(p.get('approval_status') or '').lower() not in {'approved','active'}: continue
        q=max(1,int(c.get('quantity') or 1))
        if str(p.get('product_type') or 'physical')=='physical' and q>int(p.get('stock') or 0):
            flash(f"Not enough stock for {p.get('title','item')}.",'danger'); return redirect(url_for('market_cart'))
        line=float(p.get('price') or 0)*q; subtotal+=line
        item_delivery=float(p.get('delivery_fee') or 0) if str(p.get('product_type') or 'physical')=='physical' and as_bool(p.get('delivery_available')) else 0
        delivery+=item_delivery
        items.append({'product':p,'quantity':q,'line':line,'delivery':item_delivery})
    total=round(subtotal+delivery,2); platform_fee=round(total*KOJA_PLATFORM_FEE_RATE,2); grand=round(total+platform_fee,2)
    if request.method=='POST':
        name=clean(request.form.get('recipient_name')); phone=clean(request.form.get('recipient_phone')); address=clean(request.form.get('delivery_address')); notes=clean(request.form.get('notes'))
        network=clean(request.form.get('network')).upper(); payment_phone=clean(request.form.get('payment_phone')) or phone or clean((current_user() or {}).get('phone'))
        if not items: flash('Your cart is empty.','warning'); return redirect(url_for('market_cart'))
        if grand<=0: flash('Checkout total must be greater than zero.','danger'); return redirect(url_for('market_cart'))
        if not FLW_SECRET_KEY:
            flash('Online payment is not configured. Add FLW_SECRET_KEY to Render Environment Variables.','warning'); return redirect(url_for('market_cart_checkout'))
        if network not in ('MTN','AIRTEL','ZAMTEL') or not payment_phone:
            flash('Select MTN, Airtel or Zamtel and enter the mobile-money phone number.','warning'); return redirect(url_for('market_cart_checkout'))
        created=[]
        for x in items:
            p=x['product']; qty=x['quantity']; item_total=round(x['line']+x['delivery'],2)
            commission=round(item_total*KOJA_MARKET_COMMISSION_RATE,2); item_fee=round(item_total*KOJA_PLATFORM_FEE_RATE,2)
            payload={'order_number':market_order_number(),'product_id':p.get('id'),'buyer_id':uid,'seller_id':p.get('seller_id'),'quantity':qty,'item_amount':x['line'],'delivery_fee':x['delivery'],'total_amount':item_total,'commission_amount':commission,'platform_fee':item_fee,'seller_amount':round(item_total-commission,2),'currency':p.get('currency') or 'ZMW','status':'pending','payment_method':'flutterwave','recipient_name':name or (current_user() or {}).get('name') or (current_user() or {}).get('full_name'),'recipient_phone':phone or (current_user() or {}).get('phone'),'delivery_address':address,'notes':notes,'created_at':utc_now(),'updated_at':utc_now()}
            row,err=db_insert('koja_market_orders',payload)
            if err:
                logger.error('KOJA checkout order creation failed: %s',err); flash('Checkout could not create all orders. Please try again.','danger'); return redirect(url_for('market_cart'))
            created.append(row)
        tx_ref='KOJA-CART-'+datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')+'-'+secrets.token_hex(4).upper()
        for row in created: db_update('koja_market_orders',{'id':row.get('id')},{'payment_reference':tx_ref,'updated_at':utc_now()})
        payload_fw={'tx_ref':tx_ref,'amount':int(round(grand)),'currency':'ZMW','email':clean((current_user() or {}).get('email')).lower(),'fullname':first_nonempty((current_user() or {}).get('name'),(current_user() or {}).get('full_name'),clean((current_user() or {}).get('email'))),'phone_number':payment_phone,'network':network,'order_id':str(created[0].get('id') or ''),'redirect_url':url_for('market_payment_callback',_external=True,tx_ref=tx_ref),'meta':{'koja_checkout':'cart','koja_order_ids':[str(x.get('id')) for x in created]}}
        try:
            r=requests.post(FLW_BASE_URL+'/charges?type=mobile_money_zambia',headers={'Authorization':'Bearer '+FLW_SECRET_KEY,'Content-Type':'application/json','Accept':'application/json'},json=payload_fw,timeout=30)
            body=json_or_empty(r); authorization=((body.get('meta') or {}).get('authorization') or {}) if isinstance(body,dict) else {}; redirect_url=authorization.get('redirect')
            if r.ok and str(body.get('status') or '').lower()=='success' and redirect_url:
                db_delete('koja_market_cart',{'user_id':uid}); return redirect(redirect_url)
            logger.error('KOJA cart V3 Zambia checkout failed: %s %s',r.status_code,str(body)[:1500])
        except Exception: logger.exception('KOJA cart checkout error')
        flash('Orders were created, but checkout could not be started. Please try again from My Orders.','danger'); return redirect(url_for('market_my'))
    return render_page('Secure Market Checkout',r'''
<div class="hero"><h1>🔐 Secure Checkout</h1><p>Review your cart. KOJA calculates delivery and the platform fee before payment.</p></div>
<div class="card">{% for x in items %}<p><strong>{{ x.product.title }}</strong> — {{ x.quantity }} × {{ money(x.product.price,x.product.currency) }}{% if x.delivery %} + {{ money(x.delivery,'ZMW') }} delivery{% endif %} = {{ money(x.line+x.delivery,x.product.currency) }}</p>{% else %}<p>Your cart is empty.</p>{% endfor %}<hr><p>Subtotal: <strong>{{ money(subtotal,'ZMW') }}</strong></p><p>Delivery: <strong>{{ money(delivery,'ZMW') }}</strong></p><p>KOJA platform fee: <strong>{{ money(platform_fee,'ZMW') }}</strong></p><h2>Total to pay: {{ money(grand,'ZMW') }}</h2></div>
{% if items %}<div class="card"><form method="post"><label>Recipient name</label><input name="recipient_name" required value="{{ (user or {}).get('name','') }}"><label>Delivery phone</label><input name="recipient_phone" required value="{{ (user or {}).get('phone','') }}"><label>Delivery address</label><textarea name="delivery_address" required></textarea><label>Notes</label><textarea name="notes"></textarea><hr><h3>Flutterwave Mobile Money</h3><label>Payment network</label><select name="network" required><option value="">Select network</option><option value="MTN">MTN</option><option value="AIRTEL">Airtel</option><option value="ZAMTEL">Zamtel</option></select><label>Payment phone</label><input name="payment_phone" required inputmode="tel" value="{{ (user or {}).get('phone','') }}"><button class="btn" type="submit">💳 Pay {{ money(grand,'ZMW') }} Securely</button></form></div>{% endif %}''',items=items,subtotal=subtotal,delivery=delivery,platform_fee=platform_fee,grand=grand,money=market_money,user=(current_user() or {}))

@app.route('/market/seller/subscription',methods=['GET','POST'])
@login_required
def market_seller_subscription():
    uid=(current_user() or {}).get('id'); seller=market_seller(uid)
    if not seller: return redirect(url_for('market_seller_register'))
    current=first_row('koja_market_seller_subscriptions',{'seller_id':seller.get('id')})
    if request.method=='POST':
        plan=clean(request.form.get('plan'))
        if plan not in KOJA_SELLER_PLANS: abort(400)
        payload={'seller_id':seller.get('id'),'user_id':uid,'plan':plan,'monthly_price':KOJA_SELLER_PLANS[plan],'status':'active' if plan=='free' else 'pending','started_at':utc_now(),'updated_at':utc_now()}
        if current: _,err=db_update('koja_market_seller_subscriptions',{'id':current.get('id')},payload)
        else: _,err=db_insert('koja_market_seller_subscriptions',payload)
        flash('Seller plan updated.' if not err else 'Subscription table is not installed.','success' if not err else 'danger'); return redirect(url_for('market_seller_subscription'))
    return render_page('Seller Subscription',r'''
<div class="hero"><h1>Seller Plans</h1><p>Choose the tools and visibility level that fit your store.</p></div><div class="grid">{% for key,price in plans.items() %}<div class="card"><h2>{{ key|title }}</h2><h3>{{ money(price,'ZMW') }}/month</h3><p>{% if key=='free' %}Basic selling and storefront.{% elif key=='pro' %}Featured eligibility, advanced analytics and promotions.{% else %}Business-grade selling tools, priority visibility and advanced reporting.{% endif %}</p><form method="post"><input type="hidden" name="plan" value="{{ key }}"><button class="btn">Choose {{ key|title }}</button></form></div>{% endfor %}</div><div class="card"><strong>Current:</strong> {{ current.plan if current else 'free' }} — {{ current.status if current else 'not started' }}</div>''',plans=KOJA_SELLER_PLANS,current=current,money=market_money)

@app.route('/market/feature/<product_id>',methods=['POST'])
@login_required
def market_feature_product(product_id):
    uid=(current_user() or {}).get('id'); p=market_product(product_id)
    if not p or str(p.get('seller_id'))!=str(uid): abort(403)
    days=max(1,min(30,int(request.form.get('days') or 7)))
    _,err=db_insert('koja_market_featured',{'product_id':product_id,'seller_id':uid,'days':days,'price':round(days*5,2),'status':'pending','created_at':utc_now()})
    flash('Featured placement requested.' if not err else 'Featured table is not installed.','success' if not err else 'danger'); return redirect(url_for('market_product_view',product_id=product_id))

@app.route('/market/advertise',methods=['GET','POST'])
@login_required
def market_advertise():
    uid=(current_user() or {}).get('id')
    if request.method=='POST':
        title=clean(request.form.get('title')); target=clean(request.form.get('target_url')); budget=max(0,float(request.form.get('budget') or 0)); placement=clean(request.form.get('placement')) or 'market'
        _,err=db_insert('koja_market_ads',{'advertiser_id':uid,'title':title,'target_url':target,'placement':placement,'budget':budget,'spent':0,'status':'pending','created_at':utc_now(),'updated_at':utc_now()})
        flash('Advertising campaign submitted for approval.' if not err else 'Advertising table is not installed.','success' if not err else 'danger'); return redirect(url_for('market_advertise'))
    ads=db_select('koja_market_ads',{'advertiser_id':uid},order='created_at.desc',limit=50) or []
    return render_page('KOJA Market Advertising',r'''<div class="hero"><h1>📣 KOJA Market Advertising</h1><p>Promote products, stores and offers across the marketplace.</p></div><div class="card"><form method="post"><label>Campaign title</label><input name="title" required><label>Destination URL</label><input name="target_url" placeholder="https://..." required><label>Placement</label><select name="placement"><option>market</option><option>featured</option><option>store</option></select><label>Budget (ZMW)</label><input name="budget" type="number" min="0" step="0.01" required><button class="btn">Submit Campaign</button></form></div><div class="card"><h2>My Campaigns</h2>{% for a in ads %}<p><strong>{{ a.title }}</strong> — {{ money(a.budget,'ZMW') }} — {{ a.status }}</p>{% else %}<p>No campaigns yet.</p>{% endfor %}</div>''',ads=ads,money=market_money)

@app.route('/market/review/<product_id>',methods=['POST'])
@login_required
def market_review(product_id):
    uid=(current_user() or {}).get('id'); rating=max(1,min(5,int(request.form.get('rating') or 5))); body=clean(request.form.get('review'))
    orders=db_select('koja_market_orders',{'buyer_id':uid,'product_id':product_id,'status':'eq.completed'},limit=10) or []
    if not orders: flash('Only completed purchases can be reviewed.','warning'); return redirect(url_for('market_product_view',product_id=product_id))
    _,err=db_insert('koja_market_reviews',{'product_id':product_id,'buyer_id':uid,'rating':rating,'review':body,'created_at':utc_now(),'updated_at':utc_now()})
    flash('Review submitted.' if not err else 'Review table is not installed.','success' if not err else 'danger'); return redirect(url_for('market_product_view',product_id=product_id))

@app.route('/market/earnings')
@login_required
def market_earnings():
    uid=(current_user() or {}).get('id'); rows=db_select('koja_market_ledger',{'seller_id':uid},order='created_at.desc',limit=300) or []
    gross=sum(float(x.get('gross_amount') or 0) for x in rows); fees=sum(float(x.get('platform_fee') or 0) for x in rows); commission=sum(float(x.get('commission_amount') or 0) for x in rows); net=sum(float(x.get('net_amount') or 0) for x in rows)
    return render_page('Seller Earnings',r'''<div class="hero"><h1>Seller Earnings</h1><p>Transparent transaction ledger for your KOJA Market sales.</p></div><div class="grid"><div class="card"><h3>Gross</h3><h2>{{ money(gross,'ZMW') }}</h2></div><div class="card"><h3>KOJA fees</h3><h2>{{ money(fees+commission,'ZMW') }}</h2></div><div class="card"><h3>Net</h3><h2>{{ money(net,'ZMW') }}</h2></div></div><div class="card"><table><tr><th>Date</th><th>Order</th><th>Gross</th><th>Fees</th><th>Net</th><th>Status</th></tr>{% for x in rows %}<tr><td>{{ x.created_at }}</td><td>{{ x.order_id }}</td><td>{{ money(x.gross_amount,'ZMW') }}</td><td>{{ money((x.platform_fee or 0)+(x.commission_amount or 0),'ZMW') }}</td><td>{{ money(x.net_amount,'ZMW') }}</td><td>{{ x.status }}</td></tr>{% else %}<tr><td colspan="6">No earnings yet.</td></tr>{% endfor %}</table></div>''',rows=rows,gross=gross,fees=fees,commission=commission,net=net,money=market_money)

# ---------------- KOJA BUSINESS SaaS ----------------
@app.route('/business')
@login_required
def koja_business():
    uid=(current_user() or {}).get('id'); businesses=db_select('koja_businesses',{'owner_id':uid},order='created_at.desc',limit=50) or []
    return render_page('KOJA Business',r'''<div class="hero"><h1>🏢 KOJA Business</h1><p>Run your business from one platform: POS, inventory, accounting, invoices, customers, suppliers, payroll, online store, AI, payments and delivery.</p><div class="actions"><a class="btn" href="{{ url_for('business_new') }}">+ Create Business</a>{% for b in businesses %}<a class="btn secondary" href="{{ url_for('business_dashboard',business_id=b.id) }}">{{ b.name }}</a>{% endfor %}</div></div><div class="grid"><div class="card"><h3>POS</h3><p>Record sales and issue receipts.</p></div><div class="card"><h3>Inventory</h3><p>Products, stock and stock movements.</p></div><div class="card"><h3>Accounting</h3><p>Income, expenses and profit/loss.</p></div><div class="card"><h3>CRM</h3><p>Customers and suppliers.</p></div><div class="card"><h3>Payroll</h3><p>Employees and payroll records.</p></div><div class="card"><h3>Online Store</h3><p>Connect your business catalogue to KOJA Market.</p></div><div class="card"><h3>AI Assistant</h3><p>Use KOJA AI for business analysis and planning.</p></div><div class="card"><h3>Payments & Delivery</h3><p>Connect commerce to KOJA payment and delivery workflows.</p></div></div>''',businesses=businesses)

@app.route('/business/new',methods=['GET','POST'])
@login_required
def business_new():
    uid=(current_user() or {}).get('id')
    if request.method=='POST':
        name=clean(request.form.get('name')); category=clean(request.form.get('category')) or 'General'; phone=clean(request.form.get('phone')); location=clean(request.form.get('location'))
        if not name: flash('Business name is required.','danger'); return redirect(url_for('business_new'))
        row,err=db_insert('koja_businesses',{'owner_id':uid,'name':name,'category':category,'phone':phone,'location':location,'status':'active','created_at':utc_now(),'updated_at':utc_now()})
        if err: flash('Business could not be created. Run KOJA_BUSINESS.sql.','danger'); return redirect(url_for('business_new'))
        return redirect(url_for('business_dashboard',business_id=row.get('id')))
    return render_page('Create Business',r'''<div class="hero"><h1>Create a Business</h1><p>Set up your KOJA Business workspace.</p></div><div class="card"><form method="post"><label>Business name</label><input name="name" required><label>Category</label><input name="category"><label>Phone</label><input name="phone"><label>Location</label><input name="location"><button class="btn">Create Business</button></form></div>''')

@app.route('/business/<business_id>')
@login_required
def business_dashboard(business_id):
    uid=(current_user() or {}).get('id'); b=first_row('koja_businesses',{'id':business_id,'owner_id':uid})
    if not b: abort(404)
    products=db_select('koja_business_products',{'business_id':business_id},limit=200) or []; sales=db_select('koja_business_sales',{'business_id':business_id},limit=200) or []; expenses=db_select('koja_business_expenses',{'business_id':business_id},limit=200) or []
    revenue=sum(float(x.get('total_amount') or 0) for x in sales); costs=sum(float(x.get('amount') or 0) for x in expenses); profit=revenue-costs
    return render_page('Business Dashboard',r'''<div class="hero"><h1>{{ b.name }}</h1><p>{{ b.category }} · {{ b.location or '' }}</p><div class="actions"><a class="btn" href="{{ url_for('business_products',business_id=b.id) }}">Inventory / POS</a><a class="btn secondary" href="{{ url_for('business_records',business_id=b.id) }}">Accounting</a><a class="btn secondary" href="{{ url_for('business_subscription',business_id=b.id) }}">Subscription</a><a class="btn secondary" href="{{ url_for('business_customers',business_id=b.id) }}">Customers</a><a class="btn secondary" href="{{ url_for('business_suppliers',business_id=b.id) }}">Suppliers</a><a class="btn secondary" href="{{ url_for('business_invoices',business_id=b.id) }}">Invoices</a><a class="btn secondary" href="{{ url_for('business_employees',business_id=b.id) }}">Employees</a><a class="btn secondary" href="{{ url_for('business_store',business_id=b.id) }}">Online Store</a><a class="btn secondary" href="{{ url_for('business_ai',business_id=b.id) }}">AI Assistant</a><a class="btn secondary" href="{{ url_for('business_payments',business_id=b.id) }}">Payments</a><a class="btn secondary" href="{{ url_for('business_delivery',business_id=b.id) }}">Delivery</a></div></div><div class="grid"><div class="card"><h3>Revenue</h3><h2>{{ money(revenue,'ZMW') }}</h2></div><div class="card"><h3>Expenses</h3><h2>{{ money(costs,'ZMW') }}</h2></div><div class="card"><h3>Profit</h3><h2>{{ money(profit,'ZMW') }}</h2></div><div class="card"><h3>Inventory items</h3><h2>{{ products|length }}</h2></div></div><div class="card"><h2>Business modules</h2><p>POS · Inventory · Accounting · Invoices · Customers · Suppliers · Payroll · Online Store · AI Assistant · Payments · Delivery</p></div>''',b=b,products=products,sales=sales,expenses=expenses,revenue=revenue,costs=costs,profit=profit,money=market_money)

@app.route('/business/<business_id>/products',methods=['GET','POST'])
@login_required
def business_products(business_id):
    uid=(current_user() or {}).get('id'); b=first_row('koja_businesses',{'id':business_id,'owner_id':uid})
    if not b: abort(404)
    if request.method=='POST':
        name=clean(request.form.get('name')); sku=clean(request.form.get('sku')); price=float(request.form.get('price') or 0); stock=max(0,int(request.form.get('stock') or 0)); cost=float(request.form.get('cost') or 0)
        _,err=db_insert('koja_business_products',{'business_id':business_id,'name':name,'sku':sku,'selling_price':price,'cost_price':cost,'stock':stock,'active':True,'created_at':utc_now(),'updated_at':utc_now()})
        flash('Product saved.' if not err else 'Inventory table is not installed.','success' if not err else 'danger'); return redirect(url_for('business_products',business_id=business_id))
    products=db_select('koja_business_products',{'business_id':business_id},order='created_at.desc',limit=300) or []
    return render_page('Business Inventory',r'''<div class="hero"><h1>Inventory & POS</h1><p>{{ b.name }}</p></div><div class="card"><form method="post"><label>Product / service</label><input name="name" required><label>SKU</label><input name="sku"><div class="grid"><div><label>Selling price</label><input name="price" type="number" step="0.01" min="0"></div><div><label>Cost price</label><input name="cost" type="number" step="0.01" min="0"></div><div><label>Stock</label><input name="stock" type="number" min="0" value="0"></div></div><button class="btn">Save Product</button></form></div><div class="card"><table><tr><th>Product</th><th>SKU</th><th>Price</th><th>Cost</th><th>Stock</th></tr>{% for p in products %}<tr><td>{{ p.name }}</td><td>{{ p.sku }}</td><td>{{ money(p.selling_price,'ZMW') }}</td><td>{{ money(p.cost_price,'ZMW') }}</td><td>{{ p.stock }}</td></tr>{% else %}<tr><td colspan="5">No products.</td></tr>{% endfor %}</table></div>''',b=b,products=products,money=market_money)

@app.route('/business/<business_id>/records',methods=['GET','POST'])
@login_required
def business_records(business_id):
    uid=(current_user() or {}).get('id'); b=first_row('koja_businesses',{'id':business_id,'owner_id':uid})
    if not b: abort(404)
    if request.method=='POST':
        kind=clean(request.form.get('kind')); amount=max(0,float(request.form.get('amount') or 0)); desc=clean(request.form.get('description'))
        table='koja_business_sales' if kind=='sale' else 'koja_business_expenses'; payload={'business_id':business_id,'description':desc,'total_amount':amount,'amount':amount,'created_at':utc_now()}
        _,err=db_insert(table,payload); flash('Record saved.' if not err else 'Accounting table is not installed.','success' if not err else 'danger'); return redirect(url_for('business_records',business_id=business_id))
    sales=db_select('koja_business_sales',{'business_id':business_id},order='created_at.desc',limit=300) or []; expenses=db_select('koja_business_expenses',{'business_id':business_id},order='created_at.desc',limit=300) or []
    return render_page('Business Accounting',r'''<div class="hero"><h1>Accounting & Profit/Loss</h1><p>{{ b.name }}</p></div><div class="card"><form method="post"><select name="kind"><option value="sale">Sale / income</option><option value="expense">Expense</option></select><label>Description</label><input name="description" required><label>Amount (ZMW)</label><input name="amount" type="number" min="0" step="0.01" required><button class="btn">Save Record</button></form></div><div class="grid"><div class="card"><h2>Sales</h2>{% for x in sales %}<p>{{ x.description }} — {{ money(x.total_amount,'ZMW') }}</p>{% else %}<p>No sales.</p>{% endfor %}</div><div class="card"><h2>Expenses</h2>{% for x in expenses %}<p>{{ x.description }} — {{ money(x.amount,'ZMW') }}</p>{% else %}<p>No expenses.</p>{% endfor %}</div></div>''',b=b,sales=sales,expenses=expenses,money=market_money)

@app.route('/business/<business_id>/subscription',methods=['GET','POST'])
@login_required
def business_subscription(business_id):
    uid=(current_user() or {}).get('id'); b=first_row('koja_businesses',{'id':business_id,'owner_id':uid})
    if not b: abort(404)
    current=first_row('koja_business_subscriptions',{'business_id':business_id})
    if request.method=='POST':
        plan=clean(request.form.get('plan'))
        if plan not in KOJA_BUSINESS_PLANS: abort(400)
        payload={'business_id':business_id,'owner_id':uid,'plan':plan,'monthly_price':KOJA_BUSINESS_PLANS[plan],'status':'active' if plan=='starter' else 'pending','started_at':utc_now(),'updated_at':utc_now()}
        if current: _,err=db_update('koja_business_subscriptions',{'id':current.get('id')},payload)
        else: _,err=db_insert('koja_business_subscriptions',payload)
        flash('Business plan updated.' if not err else 'Subscription table is not installed.','success' if not err else 'danger'); return redirect(url_for('business_subscription',business_id=business_id))
    return render_page('Business Subscription',r'''<div class="hero"><h1>{{ b.name }} — Business Plans</h1><p>Recurring SaaS revenue for KOJA and scalable tools for businesses.</p></div><div class="grid">{% for key,price in plans.items() %}<div class="card"><h2>{{ key|title }}</h2><h2>{{ money(price,'ZMW') }}/month</h2><p>POS, inventory, accounting, invoices, customers, suppliers, payroll, online store, AI, payments and delivery.</p><form method="post"><input type="hidden" name="plan" value="{{ key }}"><button class="btn">Choose {{ key|title }}</button></form></div>{% endfor %}</div><div class="card"><strong>Current:</strong> {{ current.plan if current else 'starter' }}</div>''',b=b,plans=KOJA_BUSINESS_PLANS,current=current,money=market_money)


# ============================================================
# KOJA MARKET V4 — COMMERCE INTEGRATION & PRODUCTION WORKFLOWS
# ============================================================

def _biz_owner(business_id):
    u=current_user() or {}; return first_row('koja_businesses', {'id':business_id,'owner_id':u.get('id')})

def _money_num(v):
    try:return round(float(v or 0),2)
    except:return 0.0

def _sync_market_order_to_business(order):
    if not order or str(order.get('status') or '').lower() not in {'paid','completed'}: return
    product=market_product(order.get('product_id'))
    if not product:return
    links=db_select('koja_business_products', {'market_product_id':order.get('product_id')}, limit=20) or []
    for bp in links:
        ref='KOJA Market order '+str(order.get('order_number') or order.get('id'))
        if db_select('koja_business_sales', {'business_id':bp.get('business_id'),'description':ref}, limit=1): continue
        qty=max(1,int(order.get('quantity') or 1))
        db_insert('koja_business_sales', {'business_id':bp.get('business_id'),'product_id':bp.get('id'),'quantity':qty,'total_amount':_money_num(order.get('item_amount')),'payment_method':order.get('payment_method') or 'market','status':'paid','description':ref,'created_at':utc_now()})
        if str(product.get('product_type') or 'physical')=='physical':
            old=max(0,int(bp.get('stock') or 0)); new=max(0,old-qty)
            db_update('koja_business_products', {'id':bp.get('id')}, {'stock':new,'updated_at':utc_now()})
            db_insert('koja_business_stock_movements', {'business_id':bp.get('business_id'),'product_id':bp.get('id'),'movement_type':'market_sale','quantity':-qty,'reference':str(order.get('order_number') or order.get('id')),'created_at':utc_now()})

@app.route('/market/seller/payouts', methods=['GET','POST'])
@login_required
def market_seller_payouts():
    uid=(current_user() or {}).get('id'); seller=market_seller(uid)
    if not seller:return redirect(url_for('market_seller_register'))
    if request.method=='POST':
        amount=_money_num(request.form.get('amount')); destination=clean(request.form.get('destination')); method=clean(request.form.get('method')) or 'mobile_money'
        if amount<=0 or not destination: flash('Enter a valid payout amount and destination.','danger')
        else:
            _,err=db_insert('koja_market_payouts',{'seller_id':seller.get('id'),'user_id':uid,'amount':amount,'currency':'ZMW','method':method,'destination':destination,'status':'requested','created_at':utc_now(),'updated_at':utc_now()})
            flash('Payout request submitted.' if not err else 'Payout table is not installed.','success' if not err else 'danger')
        return redirect(url_for('market_seller_payouts'))
    rows=db_select('koja_market_payouts',{'seller_id':seller.get('id')},order='created_at.desc',limit=100) or []
    return render_page('Seller Payouts',"""<div class='hero'><h1>Seller Payouts</h1><p>Request payment of available earnings.</p></div><div class='card'><form method='post'><label>Amount (ZMW)</label><input name='amount' type='number' min='1' step='0.01' required><label>Method</label><select name='method'><option value='mobile_money'>Mobile Money</option><option value='bank'>Bank</option></select><label>Destination / account</label><input name='destination' required><button class='btn'>Request Payout</button></form></div><div class='card'><table><tr><th>Date</th><th>Amount</th><th>Method</th><th>Status</th></tr>{% for x in rows %}<tr><td>{{ x.created_at }}</td><td>{{ money(x.amount,'ZMW') }}</td><td>{{ x.method }}</td><td>{{ x.status }}</td></tr>{% else %}<tr><td colspan='4'>No payout requests.</td></tr>{% endfor %}</table></div>""",rows=rows,money=market_money)

@app.route('/market/coupons', methods=['GET','POST'])
@login_required
def market_coupons():
    uid=(current_user() or {}).get('id')
    if request.method=='POST':
        code=clean(request.form.get('code')).upper(); pct=max(0,min(100,float(request.form.get('percent') or 0))); limit=max(0,int(request.form.get('usage_limit') or 0))
        _,err=db_insert('koja_market_coupons',{'seller_id':uid,'code':code,'discount_percent':pct,'usage_limit':limit,'active':True,'created_at':utc_now(),'updated_at':utc_now()})
        flash('Coupon created.' if not err else 'Coupon table is not installed.','success' if not err else 'danger'); return redirect(url_for('market_coupons'))
    rows=db_select('koja_market_coupons',{'seller_id':uid},order='created_at.desc',limit=100) or []
    return render_page('Market Coupons',"""<div class='hero'><h1>Coupons & Promotions</h1><p>Create discounts for customers.</p></div><div class='card'><form method='post'><label>Code</label><input name='code' required><label>Discount %</label><input name='percent' type='number' min='1' max='100' step='0.01' required><label>Usage limit</label><input name='usage_limit' type='number' min='0' value='0'><button class='btn'>Create Coupon</button></form></div><div class='card'><table><tr><th>Code</th><th>Discount</th><th>Uses</th></tr>{% for x in rows %}<tr><td>{{ x.code }}</td><td>{{ x.discount_percent }}%</td><td>{{ x.used_count or 0 }} / {{ x.usage_limit or 'unlimited' }}</td></tr>{% else %}<tr><td colspan='3'>No coupons.</td></tr>{% endfor %}</table></div>""",rows=rows)

@app.route('/market/advertising/<ad_id>/event/<event>',methods=['POST'])
def market_ad_event(ad_id,event):
    if event not in {'impression','click'}:abort(400)
    ad=first_row('koja_market_ads',{'id':ad_id})
    if not ad or str(ad.get('status'))!='active':abort(404)
    col='impressions' if event=='impression' else 'clicks'
    db_update('koja_market_ads',{'id':ad_id},{col:int(ad.get(col) or 0)+1,'updated_at':utc_now()})
    return jsonify(ok=True)

@app.route('/admin/commerce',methods=['GET','POST'])
@login_required
def admin_commerce():
    u=current_user() or {}
    if not u.get('is_admin'):abort(403)
    if request.method=='POST':
        table=clean(request.form.get('table')); rid=clean(request.form.get('id')); status=clean(request.form.get('status'))
        allowed={'koja_market_seller_subscriptions','koja_market_featured','koja_market_ads','koja_market_payouts','koja_market_payment_fees','koja_business_subscriptions','koja_business_payments'}
        if table not in allowed:abort(400)
        db_update(table,{'id':rid},{'status':status,'updated_at':utc_now()}); flash('Commercial record updated.','success'); return redirect(url_for('admin_commerce'))
    ss=db_select('koja_market_seller_subscriptions',{},order='created_at.desc',limit=100) or []
    ft=db_select('koja_market_featured',{},order='created_at.desc',limit=100) or []
    ads=db_select('koja_market_ads',{},order='created_at.desc',limit=100) or []
    payouts=db_select('koja_market_payouts',{},order='created_at.desc',limit=100) or []
    bs=db_select('koja_business_subscriptions',{},order='created_at.desc',limit=100) or []
    orders=db_select('koja_market_orders',{},limit=1000) or []
    revenue=sum(_money_num(x.get('commission_amount'))+_money_num(x.get('platform_fee')) for x in orders if str(x.get('status')) in {'paid','completed'})
    adrev=sum(_money_num(x.get('spent')) for x in ads)
    return render_page('Commerce Admin',"""<div class='hero'><h1>KOJA Commerce Admin</h1><p>Revenue, subscriptions, advertising, payouts and payments.</p></div><div class='grid'><div class='card'><h3>Market fees</h3><h2>{{ money(revenue,'ZMW') }}</h2></div><div class='card'><h3>Advertising spend</h3><h2>{{ money(adrev,'ZMW') }}</h2></div><div class='card'><h3>Orders</h3><h2>{{ orders|length }}</h2></div><div class='card'><h3>Pending payouts</h3><h2>{{ payouts|selectattr('status','equalto','requested')|list|length }}</h2></div></div>{% for title,table,rows in [('Seller subscriptions','koja_market_seller_subscriptions',ss),('Featured','koja_market_featured',ft),('Advertising','koja_market_ads',ads),('Payouts','koja_market_payouts',payouts),('Business subscriptions','koja_business_subscriptions',bs)] %}<div class='card'><h2>{{ title }}</h2>{% for x in rows[:20] %}<form method='post' style='display:flex;gap:8px;align-items:center;flex-wrap:wrap;border-bottom:1px solid var(--border);padding:8px 0'><input type='hidden' name='table' value='{{ table }}'><input type='hidden' name='id' value='{{ x.id }}'><span style='flex:1'>{{ x.id }} · {{ x.status }}</span><select name='status'><option>{{ x.status }}</option><option>pending</option><option>active</option><option>approved</option><option>rejected</option><option>paid</option><option>expired</option><option>cancelled</option></select><button class='btn'>Update</button></form>{% else %}<p>No records.</p>{% endfor %}</div>{% endfor %}""",ss=ss,ft=ft,ads=ads,payouts=payouts,bs=bs,orders=orders,revenue=revenue,adrev=adrev,money=market_money)

@app.route('/business/<business_id>/customers',methods=['GET','POST'])
@login_required
def business_customers(business_id):
    b=_biz_owner(business_id)
    if not b:abort(404)
    if request.method=='POST':
        _,err=db_insert('koja_business_customers',{'business_id':business_id,'name':clean(request.form.get('name')),'phone':clean(request.form.get('phone')),'email':clean(request.form.get('email')),'address':clean(request.form.get('address')),'notes':clean(request.form.get('notes')),'created_at':utc_now(),'updated_at':utc_now()})
        flash('Customer saved.' if not err else 'Customer table is not installed.','success' if not err else 'danger'); return redirect(url_for('business_customers',business_id=business_id))
    rows=db_select('koja_business_customers',{'business_id':business_id},order='created_at.desc',limit=500) or []
    return render_page('Business Customers',"""<div class='hero'><h1>Customers</h1><p>{{ b.name }}</p></div><div class='card'><form method='post'><label>Name</label><input name='name' required><label>Phone</label><input name='phone'><label>Email</label><input name='email' type='email'><label>Address</label><input name='address'><label>Notes</label><textarea name='notes'></textarea><button class='btn'>Add Customer</button></form></div><div class='card'><table><tr><th>Name</th><th>Phone</th><th>Email</th><th>Address</th></tr>{% for x in rows %}<tr><td>{{ x.name }}</td><td>{{ x.phone }}</td><td>{{ x.email }}</td><td>{{ x.address }}</td></tr>{% else %}<tr><td colspan='4'>No customers.</td></tr>{% endfor %}</table></div>""",b=b,rows=rows)

@app.route('/business/<business_id>/suppliers',methods=['GET','POST'])
@login_required
def business_suppliers(business_id):
    b=_biz_owner(business_id)
    if not b:abort(404)
    if request.method=='POST':
        _,err=db_insert('koja_business_suppliers',{'business_id':business_id,'name':clean(request.form.get('name')),'phone':clean(request.form.get('phone')),'email':clean(request.form.get('email')),'address':clean(request.form.get('address')),'notes':clean(request.form.get('notes')),'created_at':utc_now(),'updated_at':utc_now()})
        flash('Supplier saved.' if not err else 'Supplier table is not installed.','success' if not err else 'danger'); return redirect(url_for('business_suppliers',business_id=business_id))
    rows=db_select('koja_business_suppliers',{'business_id':business_id},order='created_at.desc',limit=500) or []
    return render_page('Business Suppliers',"""<div class='hero'><h1>Suppliers</h1><p>{{ b.name }}</p></div><div class='card'><form method='post'><label>Name</label><input name='name' required><label>Phone</label><input name='phone'><label>Email</label><input name='email' type='email'><label>Address</label><input name='address'><label>Notes</label><textarea name='notes'></textarea><button class='btn'>Add Supplier</button></form></div><div class='card'><table><tr><th>Name</th><th>Phone</th><th>Email</th></tr>{% for x in rows %}<tr><td>{{ x.name }}</td><td>{{ x.phone }}</td><td>{{ x.email }}</td></tr>{% else %}<tr><td colspan='3'>No suppliers.</td></tr>{% endfor %}</table></div>""",b=b,rows=rows)

@app.route('/business/<business_id>/invoices',methods=['GET','POST'])
@login_required
def business_invoices(business_id):
    b=_biz_owner(business_id)
    if not b:abort(404)
    customers=db_select('koja_business_customers',{'business_id':business_id},limit=300) or []
    if request.method=='POST':
        num=clean(request.form.get('invoice_number')) or ('INV-'+secrets.token_hex(4).upper()); amount=_money_num(request.form.get('amount')); customer=clean(request.form.get('customer_id')) or None
        row,err=db_insert('koja_business_invoices',{'business_id':business_id,'invoice_number':num,'customer_id':customer,'subtotal':amount,'tax_amount':0,'total_amount':amount,'status':'issued','due_date':clean(request.form.get('due_date')) or None,'notes':clean(request.form.get('notes')),'created_at':utc_now(),'updated_at':utc_now()})
        if row and not err: db_insert('koja_business_sales',{'business_id':business_id,'customer_id':customer,'invoice_id':row.get('id'),'quantity':1,'total_amount':amount,'payment_method':'invoice','status':'invoiced','description':'Invoice '+num,'created_at':utc_now()})
        flash('Invoice created.' if not err else 'Invoice table is not installed.','success' if not err else 'danger'); return redirect(url_for('business_invoices',business_id=business_id))
    rows=db_select('koja_business_invoices',{'business_id':business_id},order='created_at.desc',limit=300) or []
    return render_page('Business Invoices',"""<div class='hero'><h1>Invoices</h1><p>{{ b.name }}</p></div><div class='card'><form method='post'><label>Invoice number</label><input name='invoice_number'><label>Customer</label><select name='customer_id'><option value=''>Walk-in customer</option>{% for c in customers %}<option value='{{ c.id }}'>{{ c.name }}</option>{% endfor %}</select><label>Amount (ZMW)</label><input name='amount' type='number' min='0' step='0.01' required><label>Due date</label><input name='due_date' type='date'><label>Notes</label><textarea name='notes'></textarea><button class='btn'>Create Invoice</button></form></div><div class='card'><table><tr><th>Invoice</th><th>Total</th><th>Status</th><th>Due</th></tr>{% for x in rows %}<tr><td>{{ x.invoice_number }}</td><td>{{ money(x.total_amount,'ZMW') }}</td><td>{{ x.status }}</td><td>{{ x.due_date }}</td></tr>{% else %}<tr><td colspan='4'>No invoices.</td></tr>{% endfor %}</table></div>""",b=b,rows=rows,customers=customers,money=market_money)

@app.route('/business/<business_id>/employees',methods=['GET','POST'])
@login_required
def business_employees(business_id):
    b=_biz_owner(business_id)
    if not b:abort(404)
    if request.method=='POST':
        _,err=db_insert('koja_business_employees',{'business_id':business_id,'name':clean(request.form.get('name')),'phone':clean(request.form.get('phone')),'email':clean(request.form.get('email')),'role':clean(request.form.get('role')),'salary':_money_num(request.form.get('salary')),'pay_frequency':clean(request.form.get('frequency')) or 'monthly','status':'active','created_at':utc_now(),'updated_at':utc_now()})
        flash('Employee added.' if not err else 'Employee table is not installed.','success' if not err else 'danger'); return redirect(url_for('business_employees',business_id=business_id))
    rows=db_select('koja_business_employees',{'business_id':business_id},order='created_at.desc',limit=300) or []
    return render_page('Business Employees',"""<div class='hero'><h1>Employees & Payroll</h1><p>{{ b.name }}</p></div><div class='card'><form method='post'><label>Name</label><input name='name' required><label>Phone</label><input name='phone'><label>Email</label><input name='email' type='email'><label>Role</label><input name='role'><label>Salary</label><input name='salary' type='number' min='0' step='0.01'><label>Pay frequency</label><select name='frequency'><option>monthly</option><option>weekly</option><option>biweekly</option></select><button class='btn'>Add Employee</button></form></div><div class='card'><table><tr><th>Name</th><th>Role</th><th>Salary</th><th>Status</th></tr>{% for x in rows %}<tr><td>{{ x.name }}</td><td>{{ x.role }}</td><td>{{ money(x.salary,'ZMW') }}</td><td>{{ x.status }}</td></tr>{% else %}<tr><td colspan='4'>No employees.</td></tr>{% endfor %}</table><p><a class='btn secondary' href='{{ url_for('business_payroll',business_id=b.id) }}'>Open Payroll</a></p></div>""",b=b,rows=rows,money=market_money)

@app.route('/business/<business_id>/payroll',methods=['GET','POST'])
@login_required
def business_payroll(business_id):
    b=_biz_owner(business_id)
    if not b:abort(404)
    employees=db_select('koja_business_employees',{'business_id':business_id,'status':'active'},limit=300) or []
    if request.method=='POST':
        eid=clean(request.form.get('employee_id')); emp=first_row('koja_business_employees',{'id':eid,'business_id':business_id})
        if not emp:abort(400)
        gross=_money_num(request.form.get('gross')) or _money_num(emp.get('salary')); deductions=_money_num(request.form.get('deductions')); net=max(0,gross-deductions)
        _,err=db_insert('koja_business_payroll',{'business_id':business_id,'employee_id':eid,'period_start':clean(request.form.get('period_start')),'period_end':clean(request.form.get('period_end')),'gross_pay':gross,'deductions':deductions,'net_pay':net,'status':'pending','created_at':utc_now()})
        flash('Payroll record created.' if not err else 'Payroll table is not installed.','success' if not err else 'danger'); return redirect(url_for('business_payroll',business_id=business_id))
    rows=db_select('koja_business_payroll',{'business_id':business_id},order='created_at.desc',limit=300) or []
    return render_page('Business Payroll',"""<div class='hero'><h1>Payroll</h1><p>{{ b.name }}</p></div><div class='card'><form method='post'><label>Employee</label><select name='employee_id' required>{% for e in employees %}<option value='{{ e.id }}'>{{ e.name }} — {{ money(e.salary,'ZMW') }}</option>{% endfor %}</select><label>Period start</label><input name='period_start' type='date' required><label>Period end</label><input name='period_end' type='date' required><label>Gross pay</label><input name='gross' type='number' min='0' step='0.01'><label>Deductions</label><input name='deductions' type='number' min='0' step='0.01' value='0'><button class='btn'>Create Payroll</button></form></div><div class='card'><table><tr><th>Employee</th><th>Period</th><th>Net</th><th>Status</th></tr>{% for x in rows %}<tr><td>{{ x.employee_id }}</td><td>{{ x.period_start }} → {{ x.period_end }}</td><td>{{ money(x.net_pay,'ZMW') }}</td><td>{{ x.status }}</td></tr>{% else %}<tr><td colspan='4'>No payroll records.</td></tr>{% endfor %}</table></div>""",b=b,employees=employees,rows=rows,money=market_money)

@app.route('/business/<business_id>/store',methods=['GET','POST'])
@login_required
def business_store(business_id):
    b=_biz_owner(business_id)
    if not b:abort(404)
    current=first_row('koja_business_stores',{'business_id':business_id})
    if request.method=='POST':
        slug=clean(request.form.get('slug')).lower().replace(' ','-'); name=clean(request.form.get('store_name')) or b.get('name'); desc=clean(request.form.get('description')); published=bool(request.form.get('published'))
        payload={'business_id':business_id,'slug':slug,'store_name':name,'description':desc,'published':published,'market_enabled':True,'updated_at':utc_now()}
        if current:_,err=db_update('koja_business_stores',{'id':current.get('id')},payload)
        else:_,err=db_insert('koja_business_stores',payload)
        flash('Online store saved.' if not err else 'Store table is not installed.','success' if not err else 'danger'); return redirect(url_for('business_store',business_id=business_id))
    return render_page('Business Online Store',"""<div class='hero'><h1>Online Store</h1><p>Publish your catalogue through KOJA Market.</p></div><div class='card'><form method='post'><label>Store name</label><input name='store_name' value='{{ current.store_name if current else b.name }}' required><label>Store slug</label><input name='slug' value='{{ current.slug if current else '' }}' placeholder='my-store' required><label>Description</label><textarea name='description'>{{ current.description if current else '' }}</textarea><label><input type='checkbox' name='published' {% if current and current.published %}checked{% endif %} style='width:auto'> Publish store</label><button class='btn'>Save Store</button></form>{% if current and current.published %}<p><a class='btn secondary' href='{{ url_for('business_store_public',slug=current.slug) }}' target='_blank'>View Public Store</a></p>{% endif %}</div>""",b=b,current=current)

@app.route('/store/<slug>')
def business_store_public(slug):
    store=first_row('koja_business_stores',{'slug':slug,'published':True})
    if not store:abort(404)
    products=db_select('koja_business_products',{'business_id':store.get('business_id'),'active':True},limit=300) or []
    return render_page(store.get('store_name') or 'KOJA Store',"""<div class='hero'><h1>{{ store.store_name }}</h1><p>{{ store.description }}</p></div><div class='grid'>{% for p in products %}<div class='card'><h3>{{ p.name }}</h3><p>SKU: {{ p.sku or '—' }}</p><h2>{{ money(p.selling_price,'ZMW') }}</h2><p>Stock: {{ p.stock }}</p></div>{% else %}<div class='card'><p>No products listed.</p></div>{% endfor %}</div>""",store=store,products=products,money=market_money)

@app.route('/business/<business_id>/ai',methods=['GET','POST'])
@login_required
def business_ai(business_id):
    b=_biz_owner(business_id)
    if not b:abort(404)
    usage=db_select('koja_business_ai_usage',{'business_id':business_id},order='created_at.desc',limit=20) or []; answer=''
    if request.method=='POST':
        prompt=clean(request.form.get('prompt'))
        if prompt:
            answer,err=_ai_call(f"Business: {b.get('name')} Category: {b.get('category')}\nUSER: {prompt}",'You are KOJA Business AI. Give practical advice on sales, inventory, pricing, finance, marketing and operations. Never invent business data.',max_output_tokens=1400,timeout=50,preferred_model=None)
            if answer:db_insert('koja_business_ai_usage',{'business_id':business_id,'user_id':(current_user() or {}).get('id'),'prompt':prompt,'response_summary':answer[:4000],'tokens':0,'created_at':utc_now()})
            else:flash(_ai_error_message(err),'danger')
        else:flash('Enter a business question.','danger')
    return render_page('Business AI Assistant',"""<div class='hero'><h1>Business AI Assistant</h1><p>{{ b.name }} — pricing, inventory, sales, marketing and operations.</p></div><div class='card'><form method='post'><label>Your question</label><textarea name='prompt' rows='5' required placeholder='How can I improve monthly profit?'></textarea><button class='btn'>Ask KOJA AI</button></form>{% if answer %}<hr><div style='white-space:pre-wrap;line-height:1.75'>{{ answer }}</div>{% endif %}</div><div class='card'><h2>Recent AI usage</h2>{% for x in usage %}<p>{{ x.created_at }} — {{ x.prompt }}</p>{% else %}<p>No usage yet.</p>{% endfor %}</div>""",b=b,usage=usage,answer=answer)

@app.route('/business/<business_id>/payments',methods=['GET','POST'])
@login_required
def business_payments(business_id):
    b=_biz_owner(business_id)
    if not b:abort(404)
    if request.method=='POST':
        amount=_money_num(request.form.get('amount')); method=clean(request.form.get('method')) or 'cash'
        _,err=db_insert('koja_business_payments',{'business_id':business_id,'amount':amount,'currency':'ZMW','method':method,'provider':clean(request.form.get('provider')),'reference':clean(request.form.get('reference')),'status':'completed','created_at':utc_now()})
        flash('Payment recorded.' if not err else 'Payment table is not installed.','success' if not err else 'danger'); return redirect(url_for('business_payments',business_id=business_id))
    rows=db_select('koja_business_payments',{'business_id':business_id},order='created_at.desc',limit=300) or []
    return render_page('Business Payments',"""<div class='hero'><h1>Payments</h1><p>{{ b.name }}</p></div><div class='card'><form method='post'><label>Amount (ZMW)</label><input name='amount' type='number' min='0' step='0.01' required><label>Method</label><select name='method'><option>cash</option><option>mobile_money</option><option>bank</option><option>card</option><option>flutterwave</option></select><label>Provider</label><input name='provider'><label>Reference</label><input name='reference'><button class='btn'>Record Payment</button></form></div><div class='card'><table><tr><th>Date</th><th>Amount</th><th>Method</th><th>Status</th></tr>{% for x in rows %}<tr><td>{{ x.created_at }}</td><td>{{ money(x.amount,'ZMW') }}</td><td>{{ x.method }}</td><td>{{ x.status }}</td></tr>{% else %}<tr><td colspan='4'>No payments.</td></tr>{% endfor %}</table></div>""",b=b,rows=rows,money=market_money)

@app.route('/business/<business_id>/delivery',methods=['GET','POST'])
@login_required
def business_delivery(business_id):
    b=_biz_owner(business_id)
    if not b:abort(404)
    if request.method=='POST':
        tracking='KJB-'+secrets.token_hex(5).upper()
        _,err=db_insert('koja_business_delivery',{'business_id':business_id,'order_reference':clean(request.form.get('order_reference')),'address':clean(request.form.get('address')),'fee':_money_num(request.form.get('fee')),'status':'requested','tracking_code':tracking,'created_at':utc_now(),'updated_at':utc_now()})
        flash('Delivery requested: '+tracking if not err else 'Business delivery table is not installed.','success' if not err else 'danger'); return redirect(url_for('business_delivery',business_id=business_id))
    rows=db_select('koja_business_delivery',{'business_id':business_id},order='created_at.desc',limit=300) or []
    return render_page('Business Delivery',"""<div class='hero'><h1>Business Delivery</h1><p>{{ b.name }}</p></div><div class='card'><form method='post'><label>Order reference</label><input name='order_reference'><label>Delivery address</label><textarea name='address' required></textarea><label>Delivery fee (ZMW)</label><input name='fee' type='number' min='0' step='0.01'><button class='btn'>Request Delivery</button></form></div><div class='card'><table><tr><th>Tracking</th><th>Address</th><th>Fee</th><th>Status</th></tr>{% for x in rows %}<tr><td>{{ x.tracking_code }}</td><td>{{ x.address }}</td><td>{{ money(x.fee,'ZMW') }}</td><td>{{ x.status }}</td></tr>{% else %}<tr><td colspan='4'>No deliveries.</td></tr>{% endfor %}</table></div>""",b=b,rows=rows,money=market_money)


# ============================================================
# KOJA V7 — K100M MONETIZATION ENGINE
# ============================================================
def _money_value(v):
    try: return round(float(v or 0),2)
    except Exception: return 0.0

def _mono_order_for_ref(tx_ref):
    return first_row('koja_monetization_orders', {'payment_reference': tx_ref})

def _mono_create_checkout(user, order, network, phone):
    if not FLW_SECRET_KEY: return None, 'Flutterwave is not configured.'
    email=clean(user.get('email')).lower()
    if not email: return None, 'Your account needs an email address before payment.'
    if network not in ('MTN','AIRTEL','ZAMTEL') or not phone: return None, 'Select MTN, Airtel or Zamtel and enter the mobile-money number.'
    tx_ref='KOJA-MONO-'+uuid.uuid4().hex[:24]
    _,err=db_update('koja_monetization_orders',{'id':order.get('id')},{'payment_reference':tx_ref,'updated_at':utc_now()})
    if err: return None, 'Could not save payment reference.'
    payload={'tx_ref':tx_ref,'amount':int(round(_money_value(order.get('amount')))),'currency':'ZMW','email':email,'fullname':first_nonempty(user.get('name'),user.get('full_name'),email),'phone_number':phone,'network':network,'order_id':str(order.get('id') or ''),'redirect_url':url_for('monetization_payment_callback',_external=True,tx_ref=tx_ref),'meta':{'koja_monetization_order_id':str(order.get('id') or ''),'type':order.get('order_type')}}
    try:
        r=requests.post(FLW_BASE_URL+'/charges?type=mobile_money_zambia',headers={'Authorization':'Bearer '+FLW_SECRET_KEY,'Content-Type':'application/json','Accept':'application/json'},json=payload,timeout=30); body=json_or_empty(r)
        redirect_url=((body.get('meta') or {}).get('authorization') or {}).get('redirect') if isinstance(body,dict) else None
        if r.ok and str(body.get('status') or '').lower()=='success' and redirect_url: return redirect_url,None
        logger.error('KOJA monetization checkout failed: %s %s',r.status_code,str(body)[:1200])
    except Exception: logger.exception('KOJA monetization checkout error')
    return None,'Checkout could not be started.'

def _finalize_monetization(order, tx):
    if not order or not tx: return False
    status=str(tx.get('status') or '').lower()
    if status not in ('successful','completed'): return False
    if str(tx.get('currency') or '').upper()!='ZMW': return False
    if abs(_money_value(tx.get('amount'))-_money_value(order.get('amount'))) > 0.01: return False
    if str(order.get('status') or '').lower() in ('paid','completed'): return True
    oid=order.get('id'); typ=clean(order.get('order_type')); uid=order.get('user_id'); target=clean(order.get('target_id'))
    now=utc_now()
    if typ=='seller_plan':
        seller=first_row('koja_market_sellers',{'user_id':uid})
        if not seller: return False
        plan=clean(order.get('plan')) or 'pro'
        existing=first_row('koja_market_seller_subscriptions',{'seller_id':seller.get('id')})
        payload={'seller_id':seller.get('id'),'user_id':uid,'plan':plan,'monthly_price':_money_value(order.get('amount')),'status':'active','started_at':now,'expires_at':(datetime.now(timezone.utc)+timedelta(days=30)).isoformat(),'updated_at':now}
        if existing: db_update('koja_market_seller_subscriptions',{'id':existing.get('id')},payload)
        else: db_insert('koja_market_seller_subscriptions',payload)
    elif typ in ('boost','featured'):
        product=market_product(target) or marketplace_product(target)
        if not product: return False
        seller_id=product.get('seller_id')
        if typ=='featured':
            days=int(order.get('days') or 7)
            db_insert('koja_market_featured',{'product_id':target,'seller_id':seller_id,'days':days,'price':_money_value(order.get('amount')),'status':'active','starts_at':now,'ends_at':(datetime.now(timezone.utc)+timedelta(days=days)).isoformat(),'created_at':now})
        else:
            db_insert('koja_monetization_events',{'user_id':uid,'event_type':'boost_active','target_id':target,'amount':_money_value(order.get('amount')),'created_at':now})
    elif typ=='advertising':
        days=max(1,int(order.get('days') or 7))
        db_insert('koja_market_ads',{'advertiser_id':uid,'title':order.get('title') or 'KOJA Advertisement','target_url':order.get('target_url') or '/market','placement':order.get('placement') or 'market','budget':_money_value(order.get('amount')),'spent':0,'status':'active','starts_at':now,'ends_at':(datetime.now(timezone.utc)+timedelta(days=days)).isoformat(),'created_at':now,'updated_at':now})
    db_update('koja_monetization_orders',{'id':oid},{'status':'paid','payment_transaction_id':str(tx.get('id') or ''),'paid_at':now,'updated_at':now})
    db_insert('koja_monetization_ledger',{'order_id':oid,'user_id':uid,'order_type':typ,'gross_amount':_money_value(order.get('amount')),'platform_revenue':_money_value(order.get('amount')),'seller_payout':0,'currency':'ZMW','status':'posted','created_at':now})
    return True

@app.route('/market/monetize')
@login_required
def monetization_dashboard():
    user=current_user() or {}; uid=user.get('id')
    seller=first_row('koja_market_sellers',{'user_id':uid})
    subs=first_row('koja_market_seller_subscriptions',{'user_id':uid}) if seller else None
    orders=db_select('koja_monetization_orders',{'user_id':uid},order='created_at.desc',limit=50) or []
    return render_page('KOJA Monetization',r'''<div class="hero"><h1>🚀 KOJA Monetization</h1><p>Turn your store, products, audience and business into revenue.</p></div><div class="grid">
<div class="card"><h2>Seller Plans</h2><p>Starter K99 · Pro K299 · Business K999/month.</p><form method="post" action="{{ url_for('monetization_buy_plan') }}"><select name="plan"><option value="starter">Starter — K99/month</option><option value="pro">Pro — K299/month</option><option value="business">Business — K999/month</option></select><select name="network" required><option value="">Mobile-money network</option><option>MTN</option><option>AIRTEL</option><option>ZAMTEL</option></select><input name="phone" value="{{ user.phone or '' }}" required placeholder="Mobile-money phone"><button class="btn">Subscribe</button></form>{% if subs %}<p class="small">Current plan: <b>{{ subs.plan }}</b> · {{ subs.status }}</p>{% endif %}</div>
<div class="card"><h2>🚀 Boost</h2><form method="post" action="{{ url_for('monetization_buy_boost') }}"><input name="product_id" placeholder="Product ID" required><input name="amount" type="number" min="10" value="50"><select name="network" required><option value="">Network</option><option>MTN</option><option>AIRTEL</option><option>ZAMTEL</option></select><input name="phone" value="{{ user.phone or '' }}" required><button class="btn">Boost Product</button></form></div>
<div class="card"><h2>⭐ Featured</h2><form method="post" action="{{ url_for('monetization_buy_featured') }}"><input name="product_id" placeholder="Product ID" required><select name="days"><option value="7">7 days — K150</option><option value="14">14 days — K250</option><option value="30">30 days — K450</option></select><select name="network" required><option value="">Network</option><option>MTN</option><option>AIRTEL</option><option>ZAMTEL</option></select><input name="phone" value="{{ user.phone or '' }}" required><button class="btn">Feature Product</button></form></div>
<div class="card"><h2>📣 Advertising</h2><form method="post" action="{{ url_for('monetization_buy_ad') }}"><input name="title" placeholder="Ad title" required><input name="target_url" placeholder="Destination URL"><input name="amount" type="number" min="50" value="100"><input name="days" type="number" min="1" value="7"><select name="network" required><option value="">Network</option><option>MTN</option><option>AIRTEL</option><option>ZAMTEL</option></select><input name="phone" value="{{ user.phone or '' }}" required><button class="btn">Buy Advertising</button></form></div></div>
<div class="card"><h2>Payment History</h2><table><tr><th>Date</th><th>Type</th><th>Amount</th><th>Status</th></tr>{% for x in orders %}<tr><td>{{ x.created_at }}</td><td>{{ x.order_type }}</td><td>{{ money(x.amount,'ZMW') }}</td><td>{{ x.status }}</td></tr>{% else %}<tr><td colspan="4">No monetization payments yet.</td></tr>{% endfor %}</table></div>''',user=user,subs=subs,orders=orders,money=market_money)

def _mono_order(user, typ, amount, target_id=None, **extra):
    payload={'user_id':user.get('id'),'order_type':typ,'target_id':target_id,'amount':_money_value(amount),'currency':'ZMW','status':'pending','created_at':utc_now(),'updated_at':utc_now()}; payload.update(extra)
    return db_insert('koja_monetization_orders',payload)

def _mono_start(typ, amount, target_id=None, **extra):
    user=current_user() or {}; order,err=_mono_order(user,typ,amount,target_id,**extra)
    if err or not order: flash('Monetization order could not be created. Run KOJA_V7_MONETIZATION.sql in Supabase.','danger'); return redirect(url_for('monetization_dashboard'))
    url,msg=_mono_create_checkout(user,order,clean(request.form.get('network')).upper(),clean(request.form.get('phone')) or clean(user.get('phone')))
    if url: return redirect(url)
    flash(msg or 'Payment could not be started.','danger'); return redirect(url_for('monetization_dashboard'))

@app.route('/market/monetize/plan',methods=['POST'])
@login_required
def monetization_buy_plan():
    plans={'starter':99,'pro':299,'business':999}; plan=clean(request.form.get('plan')).lower(); return _mono_start('seller_plan',plans.get(plan,99),plan=plan)

@app.route('/market/monetize/boost',methods=['POST'])
@login_required
def monetization_buy_boost():
    amount=max(10,_money_value(request.form.get('amount'))); return _mono_start('boost',amount,clean(request.form.get('product_id')))

@app.route('/market/monetize/featured',methods=['POST'])
@login_required
def monetization_buy_featured():
    days=int(request.form.get('days') or 7); prices={7:150,14:250,30:450}; return _mono_start('featured',prices.get(days,150),clean(request.form.get('product_id')),days=days)

@app.route('/market/monetize/ad',methods=['POST'])
@login_required
def monetization_buy_ad():
    amount=max(50,_money_value(request.form.get('amount'))); days=max(1,int(request.form.get('days') or 7)); return _mono_start('advertising',amount,title=clean(request.form.get('title')),target_url=clean(request.form.get('target_url')),days=days)

@app.route('/market/monetize/callback')
@login_required
def monetization_payment_callback():
    tx_ref=clean(request.args.get('tx_ref') or request.args.get('reference')); tid=clean(request.args.get('transaction_id') or request.args.get('id')); tx=None
    if tid: tx=_flutterwave_verify(tid,tx_ref)
    if tx and not tx_ref: tx_ref=clean(tx.get('tx_ref') or tx.get('reference'))
    order=_mono_order_for_ref(tx_ref) if tx_ref else None
    if order and str(order.get('user_id'))==str((current_user() or {}).get('id')) and tx and _finalize_monetization(order,tx): flash('Payment verified and monetization feature activated.','success')
    else: flash('Payment is pending. KOJA will confirm it automatically from Flutterwave.','info')
    return redirect(url_for('monetization_dashboard'))

@app.route('/admin/monetization')
@admin_required
def admin_monetization():
    rows=db_select('koja_monetization_ledger',{},order='created_at.desc',limit=500) or []
    gross=sum(_money_value(x.get('gross_amount')) for x in rows); revenue=sum(_money_value(x.get('platform_revenue')) for x in rows)
    pending=db_select('koja_payout_requests',{'status':'pending'},limit=200) or []
    return render_page('Monetization Admin',r'''<div class="hero"><h1>💰 KOJA Revenue Control</h1><p>Platform revenue and payout requests.</p></div><div class="grid"><div class="card"><h2>Gross</h2><div style="font-size:32px;font-weight:800">{{ money(gross,'ZMW') }}</div></div><div class="card"><h2>KOJA Revenue</h2><div style="font-size:32px;font-weight:800">{{ money(revenue,'ZMW') }}</div></div><div class="card"><h2>Pending Payouts</h2><div style="font-size:32px;font-weight:800">{{ pending|length }}</div></div></div><div class="card"><h2>Revenue Ledger</h2><table><tr><th>Date</th><th>Type</th><th>Gross</th><th>KOJA</th><th>Status</th></tr>{% for x in rows %}<tr><td>{{ x.created_at }}</td><td>{{ x.order_type }}</td><td>{{ money(x.gross_amount,'ZMW') }}</td><td>{{ money(x.platform_revenue,'ZMW') }}</td><td>{{ x.status }}</td></tr>{% else %}<tr><td colspan="5">No revenue yet.</td></tr>{% endfor %}</table></div>''',rows=rows,gross=gross,revenue=revenue,pending=pending,money=market_money)

@app.route('/market/wallet')
@login_required
def seller_wallet():
    uid=(current_user() or {}).get('id'); rows=db_select('koja_market_orders',{'seller_id':uid,'status':'eq.paid'},limit=500) or []
    earned=sum(_money_value(x.get('seller_amount')) for x in rows); pending=db_select('koja_payout_requests',{'user_id':uid,'status':'pending'},limit=50) or []
    return render_page('Seller Wallet',r'''<div class="hero"><h1>💳 Seller Wallet</h1><p>Marketplace earnings after KOJA commission.</p></div><div class="grid"><div class="card"><h2>Available earnings</h2><div style="font-size:34px;font-weight:800">{{ money(earned,'ZMW') }}</div></div><div class="card"><h2>Request payout</h2><form method="post" action="{{ url_for('seller_payout_request') }}"><input name="amount" type="number" min="10" step="0.01" max="{{ earned }}" required placeholder="Amount ZMW"><input name="phone" value="{{ user.phone or '' }}" required placeholder="Mobile-money number"><button class="btn">Request Payout</button></form></div></div><div class="card"><h2>Pending requests</h2>{% for x in pending %}<p>{{ money(x.amount,'ZMW') }} · {{ x.status }} · {{ x.created_at }}</p>{% else %}<p>No pending payout requests.</p>{% endfor %}</div>''',earned=earned,pending=pending,user=current_user() or {},money=market_money)

@app.route('/market/wallet/payout',methods=['POST'])
@login_required
def seller_payout_request():
    user=current_user() or {}; amount=_money_value(request.form.get('amount')); phone=clean(request.form.get('phone')); uid=user.get('id')
    if amount<10 or not phone: flash('Enter a valid payout amount and mobile-money number.','warning'); return redirect(url_for('seller_wallet'))
    _,err=db_insert('koja_payout_requests',{'user_id':uid,'amount':amount,'currency':'ZMW','phone':phone,'status':'pending','created_at':utc_now(),'updated_at':utc_now()})
    flash('Payout request submitted for admin review.' if not err else 'Payout table is not installed. Run KOJA_V7_MONETIZATION.sql.','success' if not err else 'danger'); return redirect(url_for('seller_wallet'))



# ============================================================
# KOJA V7.1 — GROWTH, VERIFICATION, REFERRALS & AI MONETIZATION
# ============================================================

@app.route('/market/seller/verification', methods=['GET','POST'])
@login_required
def seller_verification():
    uid=(current_user() or {}).get('id')
    if request.method=='POST':
        payload={'user_id':uid,'legal_name':clean(request.form.get('legal_name')),'phone':clean(request.form.get('phone')),
                 'document_type':clean(request.form.get('document_type')),'document_number':clean(request.form.get('document_number')),
                 'status':'pending','updated_at':utc_now()}
        existing=first_row('koja_seller_verifications',{'user_id':uid})
        if existing: _,err=db_update('koja_seller_verifications',{'id':existing.get('id')},payload)
        else: _,err=db_insert('koja_seller_verifications',dict(payload,created_at=utc_now()))
        flash('Verification submitted for admin review.' if not err else 'Verification table is not installed. Run the V7 SQL.','success' if not err else 'danger')
        return redirect(url_for('seller_verification'))
    row=first_row('koja_seller_verifications',{'user_id':uid})
    return render_page('Seller Verification',r'''<div class="hero"><h1>✓ Seller Verification</h1><p>Build buyer trust and unlock verified-seller status.</p></div><div class="card"><form method="post"><input name="legal_name" value="{{ row.legal_name if row else '' }}" placeholder="Legal / business name" required><select name="document_type"><option value="NRC">NRC</option><option value="passport">Passport</option><option value="business_registration">Business registration</option></select><input name="document_number" value="{{ row.document_number if row else '' }}" placeholder="Document number" required><input name="phone" value="{{ row.phone if row else '' }}" placeholder="Phone" required><button class="btn">Submit verification</button></form>{% if row %}<p>Status: <strong>{{ row.status }}</strong></p>{% endif %}</div>''',row=row)

@app.route('/referrals')
@login_required
def referrals():
    uid=(current_user() or {}).get('id'); code=first_row('koja_referrals',{'referrer_id':uid,'referred_user_id':None})
    if not code:
        ref='KOJA-'+secrets.token_hex(4).upper(); db_insert('koja_referrals',{'referrer_id':uid,'code':ref,'status':'active','created_at':utc_now()}); code=first_row('koja_referrals',{'referrer_id':uid,'code':ref})
    rows=db_select('koja_referrals',{'referrer_id':uid},order='created_at.desc',limit=100) or []
    rewards=sum(_money_value(x.get('reward_amount')) for x in rows)
    return render_page('KOJA Referrals',r'''<div class="hero"><h1>🎁 KOJA Referrals</h1><p>Invite buyers and sellers and earn when qualifying activity is completed.</p></div><div class="card"><h2>Your referral code</h2><div style="font-size:28px;font-weight:800">{{ code.code if code else '—' }}</div><p>Share this code with new KOJA users.</p></div><div class="card"><h2>Rewards</h2><p>{{ money(rewards,'ZMW') }}</p><table><tr><th>Date</th><th>Status</th><th>Reward</th></tr>{% for x in rows %}<tr><td>{{ x.created_at }}</td><td>{{ x.status }}</td><td>{{ money(x.reward_amount,'ZMW') }}</td></tr>{% else %}<tr><td colspan="3">No referral activity yet.</td></tr>{% endfor %}</table></div>''',code=code,rows=rows,rewards=rewards,money=market_money)

@app.route('/ai/plan', methods=['GET','POST'])
@login_required
def ai_plan():
    uid=(current_user() or {}).get('id'); plans={'free':0,'plus':99,'pro':299,'business':999}
    if request.method=='POST':
        plan=clean(request.form.get('plan')).lower()
        if plan not in plans: flash('Invalid AI plan.','danger'); return redirect(url_for('ai_plan'))
        existing=first_row('koja_ai_subscriptions',{'user_id':uid})
        payload={'user_id':uid,'plan':plan,'monthly_price':plans[plan],'status':'active' if plan=='free' else 'pending','updated_at':utc_now()}
        if existing: db_update('koja_ai_subscriptions',{'id':existing.get('id')},payload)
        else: db_insert('koja_ai_subscriptions',dict(payload,created_at=utc_now()))
        flash('AI plan updated.' if plan=='free' else 'AI upgrade request created. Payment integration is required before activation.','success' if plan=='free' else 'info')
        return redirect(url_for('ai_plan'))
    current=first_row('koja_ai_subscriptions',{'user_id':uid})
    return render_page('KOJA AI Plans',r'''<div class="hero"><h1>🧠 KOJA AI Plans</h1><p>Free AI for everyone, with premium capacity for power users and businesses.</p></div><div class="grid">{% for key,price in plans.items() %}<div class="card"><h2>{{ key|title }}</h2><p style="font-size:28px;font-weight:800">{{ money(price,'ZMW') }}<small>/month</small></p><form method="post"><input type="hidden" name="plan" value="{{ key }}"><button class="btn">Choose {{ key|title }}</button></form></div>{% endfor %}</div><div class="card"><strong>Current plan:</strong> {{ current.plan if current else 'free' }}</div>''',plans=plans,current=current,money=market_money)

@app.route('/admin/growth')
@admin_required
def admin_growth():
    ver=db_select('koja_seller_verifications',{},order='created_at.desc',limit=100) or []
    refs=db_select('koja_referrals',{},order='created_at.desc',limit=100) or []
    ai=db_select('koja_ai_subscriptions',{},order='created_at.desc',limit=100) or []
    return render_page('Growth Admin',r'''<div class="hero"><h1>📈 KOJA Growth Control</h1><p>Seller verification, referrals and AI subscriptions.</p></div><div class="grid"><div class="card"><h2>Pending verification</h2><div style="font-size:32px;font-weight:800">{{ ver|selectattr('status','equalto','pending')|list|length }}</div></div><div class="card"><h2>Referrals</h2><div style="font-size:32px;font-weight:800">{{ refs|length }}</div></div><div class="card"><h2>AI subscriptions</h2><div style="font-size:32px;font-weight:800">{{ ai|length }}</div></div></div><div class="card"><h2>Seller verification</h2>{% for x in ver[:30] %}<form method="post" action="{{ url_for('admin_growth_update') }}" style="padding:8px 0;border-bottom:1px solid var(--border)"><input type="hidden" name="table" value="koja_seller_verifications"><input type="hidden" name="id" value="{{ x.id }}"><span>{{ x.legal_name }} · {{ x.status }}</span><select name="status"><option>pending</option><option>approved</option><option>rejected</option></select><button class="btn">Update</button></form>{% else %}<p>No verification records.</p>{% endfor %}</div>''',ver=ver,refs=refs,ai=ai)

@app.route('/admin/growth/update', methods=['POST'])
@admin_required
def admin_growth_update():
    table=clean(request.form.get('table')); rid=clean(request.form.get('id')); status=clean(request.form.get('status'))
    if table not in {'koja_seller_verifications','koja_ai_subscriptions'} or status not in {'pending','active','approved','rejected','cancelled'}: flash('Invalid update.','danger')
    else: db_update(table,{'id':rid},{'status':status,'updated_at':utc_now()}); flash('Growth record updated.','success')
    return redirect(url_for('admin_growth'))

@app.route('/admin/payments/reconcile', methods=['POST'])
@admin_required
def admin_payment_reconcile():
    refs=db_select('koja_market_orders',{'status':'pending'},order='created_at.asc',limit=100) or []
    checked=0; finalized=0
    for order in refs:
        txref=clean(order.get('payment_reference'))
        if not txref: continue
        checked+=1; tx=_flutterwave_verify(tx_ref=txref)
        if tx:
            verified_ref=clean(tx.get('tx_ref') or tx.get('txRef') or tx.get('reference'))
            market_order=first_row('koja_market_orders',{'payment_reference':verified_ref or txref})
            if market_order and _finalize_market_order(market_order,tx): finalized+=1
    flash(f'Payment reconciliation checked {checked} pending orders; finalized {finalized}.','success')
    return redirect(url_for('admin_monetization'))

# ============================================================
# LOCAL / RENDER START
# ============================================================

if __name__=="__main__":
    port=int(os.getenv("PORT","5000"))
    app.run(host="0.0.0.0",port=port,debug=False)

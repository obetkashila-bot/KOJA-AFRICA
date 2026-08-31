import os
import io
import uuid
import math
import secrets
import logging
from datetime import datetime, timezone
from functools import wraps
from urllib.parse import quote

import requests
from dotenv import load_dotenv
from flask import (
    Flask, request, redirect, url_for, session, render_template_string,
    flash, send_file, jsonify, abort
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

# ============================================================
# KOJA AFRICA
# Complete single-file Flask application
# Flask + Supabase REST API + Supabase Storage + Supabase Auth
#
# IMPORTANT AUTH FIX
# ------------------
# Registration creates the account in Supabase Auth using the
# supplied EMAIL + PASSWORD. The local profile is then created
# separately. This means passwords do not have to be stored in
# your public profiles table.
#
# If SUPABASE_ANON_KEY is not set, SUPABASE_SERVICE_KEY is used
# for the Auth REST calls.
#
# No psycopg / psycopg2.
# No database connection at startup.
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
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    if extra:
        headers.update(extra)
    return headers


def sb_rest_url(table):
    return f"{SUPABASE_URL}/rest/v1/{quote(str(table), safe='')}"


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


def safe_float(value):
    try:
        return float(value)
    except Exception:
        return None


# ============================================================
# SUPABASE REST HELPERS
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
            elif isinstance(value, str) and value.startswith(
                ("eq.", "neq.", "gt.", "gte.", "lt.", "lte.",
                 "in.", "is.", "like.", "ilike.")
            ):
                params[key] = value
            else:
                params[key] = f"eq.{value}"

    if order:
        params["order"] = order

    if limit:
        params["limit"] = str(limit)

    try:
        response = requests.get(
            sb_rest_url(table),
            headers=sb_headers(),
            params=params,
            timeout=20,
        )

        if not response.ok:
            logger.error(
                "SELECT %s failed: %s %s",
                table,
                response.status_code,
                response.text[:1500],
            )
            return []

        data = json_or_empty(response)
        return data if isinstance(data, list) else []

    except Exception as exc:
        logger.exception("SELECT error: %s", exc)
        return []


def db_insert(table, payload, returning="representation"):
    if not supabase_configured():
        return None, "Supabase is not configured."

    try:
        response = requests.post(
            sb_rest_url(table),
            headers=sb_headers({
                "Prefer": f"return={returning}"
            }),
            json=payload,
            timeout=20,
        )

        if not response.ok:
            logger.error(
                "INSERT %s failed: %s %s",
                table,
                response.status_code,
                response.text[:2000],
            )
            return None, response.text

        data = json_or_empty(response)

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
        response = requests.patch(
            sb_rest_url(table),
            headers=sb_headers({
                "Prefer": "return=representation"
            }),
            params=params,
            json=payload,
            timeout=20,
        )

        if not response.ok:
            logger.error(
                "UPDATE %s failed: %s %s",
                table,
                response.status_code,
                response.text[:2000],
            )
            return None, response.text

        return json_or_empty(response), None

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
        response = requests.delete(
            sb_rest_url(table),
            headers=sb_headers(),
            params=params,
            timeout=20,
        )

        if not response.ok:
            logger.error(
                "DELETE %s failed: %s %s",
                table,
                response.status_code,
                response.text[:1200],
            )
            return False, response.text

        return True, None

    except Exception as exc:
        logger.exception("DELETE error: %s", exc)
        return False, str(exc)


def table_exists(table):
    if not supabase_configured():
        return False

    try:
        response = requests.get(
            sb_rest_url(table),
            headers=sb_headers(),
            params={"select": "*", "limit": "1"},
            timeout=10,
        )
        return response.status_code < 400
    except Exception:
        return False


def first_row(table, filters):
    rows = db_select(table, filters=filters, limit=1)
    return rows[0] if rows else None


# ============================================================
# SUPABASE AUTH
# ============================================================

def supabase_auth_headers():
    key = SUPABASE_ANON_KEY or SUPABASE_SERVICE_KEY
    if not key:
        return None

    return {
        "apikey": key,
        "Content-Type": "application/json",
    }


def supabase_auth_signup(email, password, full_name="", phone="", role="student"):
    """ Create a real Supabase Auth account. Uses the admin endpoint when SERVICE KEY is available so the account is immediately confirmed. Falls back to public signup when only an anon key is available. """
    if not SUPABASE_URL:
        return None, "SUPABASE_URL is not configured."

    email = clean(email).lower()
    password = str(password or "")

    if not email or not password:
        return None, "Email and password are required."

    metadata = {
        "full_name": full_name or email,
        "phone": phone or "",
        "role": role or "student",
    }

    # Preferred: service-role admin creation.
    if SUPABASE_SERVICE_KEY:
        try:
            response = requests.post(
                f"{SUPABASE_URL}/auth/v1/admin/users",
                headers=sb_headers(),
                json={
                    "email": email,
                    "password": password,
                    "email_confirm": True,
                    "user_metadata": metadata,
                },
                timeout=20,
            )

            data = json_or_empty(response)

            if response.ok and data.get("id"):
                return data, None

            logger.error(
                "Supabase Auth admin signup failed: %s %s",
                response.status_code,
                response.text[:1500],
            )

            # If an account already exists, return a useful error.
            text = (response.text or "").lower()
            if "already" in text and "exist" in text:
                return None, "An account with this email already exists."

        except Exception as exc:
            logger.exception("Supabase Auth admin signup error: %s", exc)

    # Fallback: normal Supabase Auth signup.
    anon_key = SUPABASE_ANON_KEY or SUPABASE_SERVICE_KEY

    if not anon_key:
        return None, (
            "No Supabase Auth key is configured. "
            "Set SUPABASE_SERVICE_KEY or SUPABASE_ANON_KEY in Render."
        )

    try:
        response = requests.post(
            f"{SUPABASE_URL}/auth/v1/signup",
            headers={
                "apikey": anon_key,
                "Content-Type": "application/json",
            },
            json={
                "email": email,
                "password": password,
                "data": metadata,
            },
            timeout=20,
        )

        data = json_or_empty(response)

        if response.ok and data.get("id"):
            return data, None

        logger.error(
            "Supabase Auth signup failed: %s %s",
            response.status_code,
            response.text[:1500],
        )

        message = (
            data.get("msg")
            or data.get("message")
            or data.get("error_description")
            or response.text
            or "Supabase Auth signup failed."
        )

        return None, str(message)[:1000]

    except Exception as exc:
        logger.exception("Supabase Auth signup error: %s", exc)
        return None, str(exc)


def supabase_auth_login(email, password):
    if not SUPABASE_URL:
        return None

    key = SUPABASE_ANON_KEY or SUPABASE_SERVICE_KEY

    if not key:
        return None

    try:
        response = requests.post(
            f"{SUPABASE_URL}/auth/v1/token",
            params={"grant_type": "password"},
            headers={
                "apikey": key,
                "Content-Type": "application/json",
            },
            json={
                "email": email,
                "password": password,
            },
            timeout=20,
        )

        if not response.ok:
            logger.warning(
                "Supabase Auth password login failed: %s %s",
                response.status_code,
                response.text[:800],
            )
            return None

        return json_or_empty(response)

    except Exception as exc:
        logger.exception("Supabase Auth login error: %s", exc)
        return None


def supabase_auth_admin_delete(user_id):
    """ Used only when Auth account was created but local profile creation failed. This prevents orphaned accounts. """
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY or not user_id:
        return False

    try:
        response = requests.delete(
            f"{SUPABASE_URL}/auth/v1/admin/users/{quote(str(user_id), safe='')}",
            headers=sb_headers(),
            timeout=20,
        )
        return response.ok
    except Exception:
        logger.exception("Could not remove orphan Auth user.")
        return False


# ============================================================
# USER / PROFILE HELPERS
# ============================================================

def find_user_by_email(email):
    email = clean(email).lower()

    if not email:
        return None

    # profiles is the preferred application profile table.
    for table in ("profiles", "koja_users", "users", "KOJA ZM"):
        if not table_exists(table):
            continue

        rows = db_select(
            table,
            filters={"email": email},
            limit=1
        )

        if rows:
            return rows[0]

    return None


def find_user_by_id(user_id):
    if not user_id:
        return None

    for table in ("profiles", "koja_users", "users", "KOJA ZM"):
        if not table_exists(table):
            continue

        rows = db_select(
            table,
            filters={"id": user_id},
            limit=1
        )

        if rows:
            return rows[0]

    return None


def login_user(user, auth_session=None):
    session.clear()

    session["user"] = {
        "id": str(user.get("id")),
        "name": first_nonempty(
            user.get("full_name"),
            user.get("name"),
            user.get("email"),
            "KOJA User",
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
        session["supabase_access_token"] = auth_session.get(
            "access_token"
        )
        session["supabase_refresh_token"] = auth_session.get(
            "refresh_token"
        )

    session.permanent = True


def current_user():
    return session.get("user")


def password_matches(user, password):
    """ Kept for compatibility with older KOJA local-password rows. New registrations use Supabase Auth instead. """
    stored = first_nonempty(
        user.get("password_hash"),
        user.get("encrypted_password"),
    )

    if not stored or not password:
        return False

    try:
        return check_password_hash(stored, password)
    except Exception:
        return False


def insert_profile_compatible(user_id, email, full_name="", phone="", role="student"):
    """ Tries several profile payloads because existing KOJA databases may have different profile columns. Password is deliberately NOT inserted into profiles. """

    if not table_exists("profiles"):
        return None, (
            "The profiles table does not exist. "
            "Create a profiles table or use the existing KOJA profile table."
        )

    base = {
        "id": str(user_id),
        "email": email,
        "full_name": full_name or email,
        "name": full_name or email,
        "phone": phone or None,
        "role": role or "student",
        "is_admin": False,
        "is_active": True,
    }

    # First attempt: common modern KOJA schema.
    attempts = [
        base,
        {
            "id": str(user_id),
            "email": email,
            "full_name": full_name or email,
            "phone": phone or None,
            "role": role or "student",
            "is_admin": False,
        },
        {
            "id": str(user_id),
            "email": email,
            "full_name": full_name or email,
            "phone": phone or None,
            "role": role or "student",
        },
        {
            "id": str(user_id),
            "email": email,
            "full_name": full_name or email,
            "phone": phone or None,
        },
        {
            "id": str(user_id),
            "email": email,
            "full_name": full_name or email,
        },
        {
            "id": str(user_id),
            "email": email,
        },
    ]

    errors = []

    for index, payload in enumerate(attempts, start=1):
        row, error = db_insert("profiles", payload)

        if not error:
            logger.info(
                "Profile created using compatible payload attempt %s.",
                index
            )
            return row or payload, None

        errors.append(str(error)[:1000])

        # Do not keep retrying if this is a duplicate/unique error.
        text = str(error).lower()
        if "duplicate key" in text or "already exists" in text:
            existing = find_user_by_id(user_id)
            if existing:
                return existing, None

    logger.error(
        "All profile creation attempts failed: %s",
        " | ".join(errors)
    )

    return None, " | ".join(errors[-2:])


def create_local_profile(user_id, email, full_name="", phone="", role="student"):
    return insert_profile_compatible(
        user_id=user_id,
        email=email,
        full_name=full_name,
        phone=phone,
        role=role,
    )


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

    path = (
        f"{folder.strip('/')}/"
        f"{uuid.uuid4().hex}_{filename}"
    )

    mime = file_storage.mimetype or "application/octet-stream"

    try:
        response = requests.post(
            sb_storage_url(path),
            headers=sb_headers({
                "Content-Type": mime,
                "x-upsert": "true",
            }),
            data=data,
            timeout=60,
        )

        if not response.ok:
            return None, response.text[:1200]

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
        response = requests.delete(
            sb_storage_url(path),
            headers=sb_headers(),
            timeout=20,
        )
        return response.ok
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
            return redirect(
                url_for(
                    "login",
                    next=request.path
                )
            )
        return fn(*args, **kwargs)

    return wrapper


def admin_required(fn):
@wraps(fn)
    def wrapper(*args, **kwargs):
        user = current_user()

        if not user:
            flash(
                "Administrator login required.",
                "warning"
            )
            return redirect(url_for("login"))

        if not user.get("is_admin"):
            flash(
                "Administrator access required.",
                "danger"
            )
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

        if (
            user.get("role") not in ("driver", "admin")
            and not user.get("is_admin")
        ):
            flash(
                "Driver account required.",
                "danger"
            )
            return redirect(url_for("dashboard"))

        return fn(*args, **kwargs)

    return wrapper


def log_activity(action, description="", user_id=None):
    uid = user_id or (current_user() or {}).get("id")

    payload = {
        "action": action,
        "description": description,
    }

    if uid:
        payload["user_id"] = uid

    try:
        if table_exists("activity_logs"):
            db_insert("activity_logs", payload)
    except Exception:
        logger.exception("Activity log failed.")


# ============================================================
# GEOLOCATION
# ============================================================

def haversine_km(lat1, lon1, lat2, lon2):
    radius = 6371.0088

    p1 = math.radians(lat1)
    p2 = math.radians(lat2)

    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)

    a = (
        math.sin(dp / 2) ** 2
        + math.cos(p1)
        * math.cos(p2)
        * math.sin(dl / 2) ** 2
    )

    return radius * 2 * math.atan2(
        math.sqrt(a),
        math.sqrt(1 - a)
    )


def latest_driver_locations():
    rows = db_select(
        "driver_locations",
        order="created_at.desc",
        limit=1000
    )

    latest = {}

    for row in rows:
        uid = row.get("driver_id") or row.get("user_id")

        if uid and str(uid) not in latest:
            latest[str(uid)] = row

    return latest


def get_driver_provider(user_id):
    if not user_id:
        return None

    return first_row(
        "service_providers",
        {
            "user_id": user_id,
            "provider_type": "driver",
        }
    )


def ensure_driver_provider(user):
    provider = get_driver_provider(user.get("id"))

    if provider:
        return provider, None

    payload = {
        "id": str(uuid.uuid4()),
        "user_id": user.get("id"),
        "provider_type": "driver",
        "full_name": user.get("name") or "Driver",
        "phone": user.get("phone") or None,
        "email": user.get("email") or None,
        "verification_status": "pending",
        "is_available": False,
        "is_active": True,
    }

    provider, error = db_insert(
        "service_providers",
        payload
    )

    if error:
        return None, error

    return provider or payload, None


# ============================================================
# HTML
# ============================================================

BASE_HTML = r""" <!doctype html> <html lang="en"> <head> <meta charset="utf-8"> <meta name="viewport" content="width=device-width, initial-scale=1"> <title>{{ title or "KOJA AFRICA" }}</title> <style> *{box-sizing:border-box} body{ margin:0; font-family:Arial,sans-serif; background:#f5f7fb; color:#18212f; } nav{ background:#111827; color:white; padding:14px; position:sticky; top:0; z-index:20; } nav .brand{ font-weight:800; font-size:20px; margin-right:18px; } nav a{ color:white; text-decoration:none; margin:5px; display:inline-block; } .container{ width:min(1100px,94%); margin:24px auto; } .card{ background:white; border-radius:14px; padding:20px; margin:14px 0; box-shadow:0 3px 16px rgba(0,0,0,.07); } .grid{ display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:14px; } input,select,textarea,button{ width:100%; padding:12px; margin:7px 0; border:1px solid #d1d5db; border-radius:9px; font-size:15px; } textarea{min-height:130px} button,.btn{ background:#111827; color:white; border:0; cursor:pointer; text-decoration:none; display:inline-block; text-align:center; } .btn{ padding:11px 15px; border-radius:9px; margin:4px 0; } .success{background:#dcfce7;padding:12px;border-radius:8px} .danger{background:#fee2e2;padding:12px;border-radius:8px} .warning{background:#fef3c7;padding:12px;border-radius:8px} .muted{color:#6b7280} .stat{ font-size:28px; font-weight:800; } table{ width:100%; border-collapse:collapse; overflow:auto; } th,td{ padding:9px; border-bottom:1px solid #e5e7eb; text-align:left; } pre{ white-space:pre-wrap; word-wrap:break-word; } </style> </head> <body> <nav> <span class="brand">KOJA AFRICA</span> <a href="{{ url_for('home') }}">Home</a> {% if user %} <a href="{{ url_for('dashboard') }}">Dashboard</a> <a href="{{ url_for('services') }}">Services</a> <a href="{{ url_for('questions') }}">Questions</a> <a href="{{ url_for('assignments') }}">Assignments</a> <a href="{{ url_for('universities') }}">Universities</a> <a href="{{ url_for('deliveries') }}">Deliveries</a> <a href="{{ url_for('drivers') }}">Drivers</a> {% if user.role in ['driver','admin'] or user.is_admin %} <a href="{{ url_for('driver_dashboard') }}">Driver</a> {% endif %} {% if user.is_admin %} <a href="{{ url_for('admin') }}">Admin</a> {% endif %} <a href="{{ url_for('logout') }}">Logout</a> {% else %} <a href="{{ url_for('login') }}">Login</a> <a href="{{ url_for('register') }}">Register</a> {% endif %} </nav> <div class="container"> {% with messages=get_flashed_messages(with_categories=true) %} {% for category, message in messages %} <div class="{{ category }}">{{ message }}</div> {% endfor %} {% endwith %} {{ body|safe }} </div> <footer class="container muted"> KOJA AFRICA — Knowledge • Questions • Answers </footer> </body> </html> """


def render_page(title, body_template, **context):
    context["user"] = current_user()

    body = render_template_string(
        body_template,
        **context
    )

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
    return render_page(
        "KOJA AFRICA",
        r""" <div class="card"> <h1>KOJA AFRICA</h1> <p>Knowledge • Questions • Answers</p> <p> Academic services, university applications, CV creation, farmer registration, professional bookings and delivery services. </p> {% if not user %} <a class="btn" href="{{ url_for('register') }}">Create Account</a> <a class="btn" href="{{ url_for('login') }}">Login</a> {% endif %} </div> <div class="grid"> <div class="card"> <h3>Academic</h3> <p>Questions, assignments and learning resources.</p> <a class="btn" href="{{ url_for('questions') }}">Questions</a> </div> <div class="card"> <h3>University</h3> <p>Choose a university, programme and academic year.</p> <a class="btn" href="{{ url_for('universities') }}">Universities</a> </div> <div class="card"> <h3>CV</h3> <p>Create a professional CV.</p> <a class="btn" href="{{ url_for('cv') }}">Create CV</a> </div> <div class="card"> <h3>Farmers</h3> <p>Submit agricultural registration information.</p> <a class="btn" href="{{ url_for('farmer') }}">Farmer Portal</a> </div> <div class="card"> <h3>Doctors</h3> <p>Find a doctor and request an appointment.</p> <a class="btn" href="{{ url_for('doctors') }}">Doctors</a> </div> <div class="card"> <h3>Teachers</h3> <p>Find teachers/tutors by subject and grade.</p> <a class="btn" href="{{ url_for('teachers') }}">Teachers</a> </div> <div class="card"> <h3>Deliveries</h3> <p>Find nearby drivers and send delivery requests.</p> <a class="btn" href="{{ url_for('deliveries') }}">Delivery</a> </div> <div class="card"> <h3>Live GPS</h3> <p>Drivers can share their live location.</p> <a class="btn" href="{{ url_for('tracking') }}">Driver GPS</a> </div> </div> """
    )


@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "application": APP_NAME,
        "supabase_configured": supabase_configured(),
        "profiles_table_available": table_exists("profiles"),
        "gps_table_available": table_exists("driver_locations"),
        "timestamp": utc_now(),
        "python": os.sys.version.split()[0],
    })


# ============================================================
# REGISTER
# ============================================================

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        full_name = clean(request.form.get("full_name"))
        email = clean(request.form.get("email")).lower()
        phone = clean(request.form.get("phone"))
        password = request.form.get("password", "")
        role = clean(request.form.get("role")) or "student"

        if role not in (
            "student",
            "driver",
            "teacher",
            "doctor"
        ):
            role = "student"

        if not full_name or not email or not password:
            flash(
                "Full name, email and password are required.",
                "danger"
            )
            return redirect(url_for("register"))

        if len(password) < 6:
            flash(
                "Password must contain at least 6 characters.",
                "danger"
            )
            return redirect(url_for("register"))

        if not supabase_configured():
            flash(
                "Supabase is not configured in Render. "
                "Set SUPABASE_URL and SUPABASE_SERVICE_KEY.",
                "danger"
            )
            return redirect(url_for("register"))

        # Check the application's profile table first.
        existing_profile = find_user_by_email(email)

        if existing_profile:
            flash(
                "An account with this email already exists. "
                "Please log in.",
                "warning"
            )
            return redirect(url_for("login"))

        # Create the real authentication account.
        auth_user, auth_error = supabase_auth_signup(
            email=email,
            password=password,
            full_name=full_name,
            phone=phone,
            role=role,
        )

        if auth_error or not auth_user:
            logger.error(
                "Registration Auth creation failed: %s",
                auth_error
            )
            flash(
                "Registration failed: "
                + str(auth_error or "Supabase Auth could not create the account.")[:1200],
                "danger"
            )
            return redirect(url_for("register"))

        user_id = str(auth_user.get("id"))

        # Create local application profile.
        profile, profile_error = create_local_profile(
            user_id=user_id,
            email=email,
            full_name=full_name,
            phone=phone,
            role=role,
        )

        if profile_error or not profile:
            logger.error(
                "Local profile creation failed after Auth creation: %s",
                profile_error
            )

            # Prevent a half-created account where possible.
            supabase_auth_admin_delete(user_id)

            flash(
                "Registration failed while creating your KOJA profile. "
                "Exact database error: "
                + str(profile_error or "Unknown profile error")[:1500],
                "danger"
            )
            return redirect(url_for("register"))

        # Log in immediately.
        login_user(
            profile,
            auth_session=auth_user
        )

        log_activity(
            "registration",
            "New KOJA account registered through Supabase Auth.",
            user_id=user_id,
        )

        flash(
            "Account created successfully. "
            "You can now use your email and password to log in.",
            "success"
        )

        if role == "driver":
            return redirect(url_for("driver_register"))

        return redirect(url_for("dashboard"))

    return render_page(
        "Register",
        r""" <div class="card"> <h2>Create KOJA Account</h2> <p class="muted"> Use your email and password. The password is handled by Supabase Authentication and is not stored in the public KOJA profile table. </p> <form method="post"> <label>Full Name</label> <input name="full_name" required> <label>Email</label> <input type="email" name="email" required> <label>Phone</label> <input name="phone"> <label>Account Type</label> <select name="role"> <option value="student">Student / Customer</option> <option value="driver">Delivery Driver</option> <option value="teacher">Teacher / Tutor</option> <option value="doctor">Doctor</option> </select> <label>Password</label> <input type="password" name="password" minlength="6" required> <button type="submit">Create Account</button> </form> <p> Already registered? <a href="{{ url_for('login') }}">Login</a> </p> </div> """
    )


# ============================================================
# LOGIN
# ============================================================

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = clean(
            request.form.get("email")
        ).lower()

        password = request.form.get(
            "password",
            ""
        )

        if not email or not password:
            flash(
                "Email and password are required.",
                "danger"
            )
            return redirect(url_for("login"))

        # First try the new Supabase Auth account.
        auth = supabase_auth_login(
            email,
            password
        )

        if auth and auth.get("user"):
            auth_user = auth["user"]

            profile = find_user_by_id(
                auth_user.get("id")
            )

            if not profile:
                metadata = auth_user.get(
                    "user_metadata",
                    {}
                ) or {}

                profile, profile_error = create_local_profile(
                    user_id=auth_user.get("id"),
                    email=auth_user.get("email") or email,
                    full_name=metadata.get(
                        "full_name",
                        ""
                    ),
                    phone=metadata.get(
                        "phone",
                        ""
                    ),
                    role=metadata.get(
                        "role",
                        "student"
                    ),
                )

                if profile_error:
                    logger.error(
                        "Profile auto-create on login failed: %s",
                        profile_error
                    )
                    flash(
                        "Login succeeded in Supabase Auth, "
                        "but the KOJA profile could not be created: "
                        + str(profile_error)[:1000],
                        "danger"
                    )
                    return redirect(url_for("login"))

            if profile.get("is_active") is False:
                flash(
                    "This account is inactive.",
                    "danger"
                )
                return redirect(url_for("login"))

            login_user(
                profile,
                auth_session=auth
            )

            log_activity(
                "login",
                "User logged into KOJA through Supabase Auth."
            )

            next_url = request.args.get("next", "")

            if next_url.startswith("/"):
                return redirect(next_url)

            return redirect(
                url_for("dashboard")
            )

        # Backward compatibility for old local KOJA accounts
        # which already contain password_hash.
        local_user = find_user_by_email(email)

        if local_user and password_matches(
            local_user,
            password
        ):
            if local_user.get("is_active") is False:
                flash(
                    "This account is inactive.",
                    "danger"
                )
                return redirect(url_for("login"))

            login_user(local_user)

            log_activity(
                "login",
                "Legacy local-password login."
            )

            return redirect(
                request.args.get("next")
                if request.args.get(
                    "next",
                    ""
                ).startswith("/")
                else url_for("dashboard")
            )

        flash(
            "Invalid login credentials. "
            "Use the same email and password used when creating "
            "your KOJA account.",
            "danger"
        )

        return redirect(url_for("login"))

    return render_page(
        "Login",
        r""" <div class="card"> <h2>KOJA Login</h2> <form method="post"> <label>Email</label> <input type="email" name="email" autocomplete="email" required> <label>Password</label> <input type="password" name="password" autocomplete="current-password" required> <button type="submit">Login</button> </form> <p> No account? <a href="{{ url_for('register') }}">Create one</a> </p> </div> """
    )


@app.route("/logout")
def logout():
    if current_user():
        log_activity(
            "logout",
            "User logged out."
        )

    session.clear()

    flash(
        "You have been logged out.",
        "success"
    )

    return redirect(url_for("home"))


# ============================================================
# DASHBOARD / SERVICES
# ============================================================

@app.route("/dashboard")
@login_required
def dashboard():
    user = current_user()

    questions_count = len(
        db_select(
            "questions",
            filters={"student_id": user["id"]},
            limit=1000
        )
    )

    deliveries_count = len(
        db_select(
            "deliveries",
            filters={"customer_id": user["id"]},
            limit=1000
        )
    )

    appointments_count = len(
        db_select(
            "appointments",
            filters={"client_id": user["id"]},
            limit=1000
        )
    )

    return render_page(
        "Dashboard",
        r""" <div class="card"> <h2>Welcome, {{ user.name }}</h2> <p>{{ user.email }}</p> </div> <div class="grid"> <div class="card"> <div class="stat">{{ questions_count }}</div> <p>Academic Questions</p> </div> <div class="card"> <div class="stat">{{ deliveries_count }}</div> <p>Deliveries</p> </div> <div class="card"> <div class="stat">{{ appointments_count }}</div> <p>Appointments</p> </div> <div class="card"> <div class="stat"> {{ "ADMIN" if user.is_admin else user.role|upper }} </div> <p>Account</p> </div> </div> <div class="card"> <h3>KOJA Services</h3> <div class="grid"> <a class="btn" href="{{ url_for('cv') }}">Create CV</a> <a class="btn" href="{{ url_for('universities') }}">University Application</a> <a class="btn" href="{{ url_for('farmer') }}">Farmer Registration</a> <a class="btn" href="{{ url_for('doctors') }}">Doctor Booking</a> <a class="btn" href="{{ url_for('teachers') }}">Teacher Booking</a> <a class="btn" href="{{ url_for('drivers') }}">Find Driver / Delivery</a> {% if user.role in ['driver','admin'] or user.is_admin %} <a class="btn" href="{{ url_for('driver_dashboard') }}">Driver Dashboard</a> {% endif %} </div> </div> """,
        questions_count=questions_count,
        deliveries_count=deliveries_count,
        appointments_count=appointments_count,
    )


@app.route("/services")
@login_required
def services():
    return render_page(
        "Services",
        r""" <div class="card"> <h2>KOJA Services</h2> <div class="grid"> <a class="btn" href="{{ url_for('questions') }}">Academic Questions</a> <a class="btn" href="{{ url_for('assignments') }}">Assignments</a> <a class="btn" href="{{ url_for('cv') }}">CV</a> <a class="btn" href="{{ url_for('universities') }}">University Applications</a> <a class="btn" href="{{ url_for('farmer') }}">Farmer Registration</a> <a class="btn" href="{{ url_for('doctors') }}">Doctors</a> <a class="btn" href="{{ url_for('teachers') }}">Teachers</a> <a class="btn" href="{{ url_for('deliveries') }}">Deliveries</a> </div> </div> """
    )


# ============================================================
# QUESTIONS
# ============================================================

@app.route("/questions", methods=["GET", "POST"])
@login_required
def questions():
    user = current_user()

    if request.method == "POST":
        question_text = clean(
            request.form.get("question")
        )
        subject = clean(
            request.form.get("subject")
        )

        if not question_text:
            flash(
                "Enter your question.",
                "danger"
            )
            return redirect(url_for("questions"))

        payload = {
            "id": str(uuid.uuid4()),
            "student_id": str(user["id"]),
            "student_name": user.get("name") or "KOJA Student",
            "question": question_text,
            "answer": "",
            "answer_by": "",
            "subject": subject or None,
            "status": "pending",
            "created_at": utc_now(),
        }

        row, error = db_insert(
            "questions",
            payload
        )

        if error:
            flash(
                "Question could not be submitted. "
                + str(error)[:900],
                "danger"
            )
        else:
            flash(
                "Question submitted.",
                "success"
            )
            log_activity(
                "question_created",
                "Student submitted an academic question."
            )

        return redirect(
            url_for("questions")
        )

    rows = db_select(
        "questions",
        filters={"student_id": user["id"]},
        order="created_at.desc",
        limit=100
    )

    return render_page(
        "Questions",
        r""" <div class="card"> <h2>Ask an Academic Question</h2> <form method="post"> <label>Subject</label> <input name="subject"> <label>Question</label> <textarea name="question" required></textarea> <button type="submit">Submit Question</button> </form> </div> <div class="card"> <h2>My Questions</h2> {% for q in rows %} <div class="card"> <strong>{{ q.get("subject") or "Academic" }}</strong> <p>{{ q.get("question") or q.get("question_text") }}</p> {% if q.get("answer") %} <h4>Answer</h4> <pre>{{ q.get("answer") }}</pre> {% endif %} <p class="muted"> Status: {{ q.get("status") or "Submitted" }} </p> </div> {% else %} <p>No questions submitted yet.</p> {% endfor %} </div> """,
        rows=rows,
    )


# ============================================================
@app.route("/assignments", methods=["GET", "POST"])
@login_required
def assignments():
    user = current_user() or {}

    if request.method == "POST":
        title = clean(request.form.get("title"))
        description = clean(request.form.get("description"))
        subject = clean(request.form.get("subject"))
        course = clean(request.form.get("course"))
        class_level = clean(request.form.get("class_level"))
        question = clean(request.form.get("question"))

        uploaded = None
        f = request.files.get("file")

        if not title:
            flash("Assignment title is required.", "danger")
            return redirect(url_for("assignments"))

        # Upload file first, if supplied
        if f and f.filename:
            uploaded, upload_error = upload_storage(f, "assignments")

            if upload_error:
                flash(
                    "Assignment file upload failed: " +
                    str(upload_error)[:500],
                    "danger"
                )
                return redirect(url_for("assignments"))

        # Build only columns supported by the KOJA assignments schema
        payload = {
            "student_id": user.get("id"),
            "title": title,
            "description": description,
            "subject": subject,
            "course": course,
            "class_level": class_level,
            "status": "submitted",
            "email": user.get("email"),
            "student_name": (
                user.get("student_name")
                or user.get("full_name")
                or user.get("name")
            ),
            "student_email": user.get("email"),
            "institution": user.get("institution"),
            "question": question or description,
            "created_at": utc_now(),
            "updated_at": utc_now()
        }

        if uploaded:
            payload.update({
                "file_name": uploaded.get("file_name"),
                "file_path": uploaded.get("path"),
                "file_url": uploaded.get("url"),
                "file_size": uploaded.get("file_size", 0),
                "mime_type": uploaded.get(
                    "mime_type",
                    "application/octet-stream"
                )
            })

        try:
            row, error = db_insert("assignments", payload)

            if error:
                logger.error(
                    "ASSIGNMENT INSERT ERROR: %s",
                    str(error)
                )

                flash(
                    "Assignment could not be saved: " +
                    str(error)[:700],
                    "danger"
                )
                return redirect(url_for("assignments"))

            flash(
                "Assignment uploaded successfully.",
                "success"
            )

        except Exception as e:
            logger.exception("ASSIGNMENT SAVE ERROR")

            flash(
                "Assignment could not be saved: " +
                str(e)[:700],
                "danger"
            )

        return redirect(url_for("assignments"))

    # GET
    try:
        rows = db_select(
            "assignments",
            order="created_at.desc",
            limit=100
        )
    except Exception as e:
        logger.exception("ASSIGNMENT LIST ERROR")
        rows = []
        flash(
            "Could not load assignments: " +
            str(e)[:500],
            "danger"
        )

    return render_page(
        "Assignments",
        r"""
        <div class="card">
            <h2>Upload Assignment</h2>

            <form method="post"
                  enctype="multipart/form-data">

                <label>Assignment Title</label>
                <input
                    name="title"
                    required
                    placeholder="e.g. Biology Assignment 1">

                <label>Subject</label>
                <input
                    name="subject"
                    placeholder="Biology, Chemistry, Mathematics...">

                <label>Course</label>
                <input
                    name="course"
                    placeholder="Course name">

                <label>Class Level</label>
                <input
                    name="class_level"
                    placeholder="Grade 12 / Year 1 / Diploma...">

                <label>Description / Question</label>
                <textarea
                    name="description"
                    placeholder="Enter assignment instructions or description"></textarea>

                <label>Question</label>
                <textarea
                    name="question"
                    placeholder="Enter the actual question if applicable"></textarea>

                <label>Assignment File</label>
                <input
                    type="file"
                    name="file"
                    accept=".pdf,.doc,.docx,.txt,.jpg,.jpeg,.png">

                <button type="submit">
                    Upload Assignment
                </button>
            </form>
        </div>

        <div class="card">
            <h2>Assignments</h2>

            {% for item in rows %}

            <div class="card">
                <h3>
                    {{ item.get("title") or "Assignment" }}
                </h3>

                {% if item.get("subject") %}
                <p>
                    <strong>Subject:</strong>
                    {{ item.get("subject") }}
                </p>
                {% endif %}

                {% if item.get("course") %}
                <p>
                    <strong>Course:</strong>
                    {{ item.get("course") }}
                </p>
                {% endif %}

                <p>
                    {{ item.get("question")
                       or item.get("description")
                       or "" }}
                </p>

                <p>
                    <span class="badge">
                        {{ item.get("status") or "Submitted" }}
                    </span>
                </p>

                {% if item.get("file_url") %}
                <a
                    class="btn"
                    href="{{ item.get('file_url') }}"
                    target="_blank">
                    Open Assignment File
                </a>
                {% elif item.get("file_path") %}
                <a
                    class="btn"
                    href="/assignment/{{ item.get('id') }}/download">
                    Download Assignment
                </a>
                {% endif %}

                {% if item.get("answer_file_url") %}
                <a
                    class="btn success"
                    href="{{ item.get('answer_file_url') }}"
                    target="_blank">
                    Download Answer
                </a>
                {% endif %}

                {% if item.get("answered_file_url") %}
                <a
                    class="btn success"
                    href="{{ item.get('answered_file_url') }}"
                    target="_blank">
                    Download Answered File
                </a>
                {% endif %}
            </div>

            {% else %}

            <p>No assignments found.</p>

            {% endfor %}
        </div>
        """,
        rows=rows
    )
    

# ============================================================
# CV
# ============================================================

@app.route("/cv", methods=["GET", "POST"])
@login_required
def cv():
    user = current_user()

    if request.method == "POST":
        data = {
            "full_name": clean(
                request.form.get("full_name")
            ),
            "phone": clean(
                request.form.get("phone")
            ),
            "email": clean(
                request.form.get("email")
            ),
            "address": clean(
                request.form.get("address")
            ),
            "profile": clean(
                request.form.get("profile")
            ),
            "education": clean(
                request.form.get("education")
            ),
            "experience": clean(
                request.form.get("experience")
            ),
            "skills": clean(
                request.form.get("skills")
            ),
            "references": clean(
                request.form.get("references")
            ),
        }

        return render_page(
            "CV Preview",
            r""" <div class="card"> <h1>{{ data.full_name }}</h1> <p> {{ data.phone }} | {{ data.email }} | {{ data.address }} </p> {% if data.profile %} <h2>Professional Profile</h2> <pre>{{ data.profile }}</pre> {% endif %} {% if data.education %} <h2>Education</h2> <pre>{{ data.education }}</pre> {% endif %} {% if data.experience %} <h2>Work Experience</h2> <pre>{{ data.experience }}</pre> {% endif %} {% if data.skills %} <h2>Skills</h2> <pre>{{ data.skills }}</pre> {% endif %} {% if data.references %} <h2>References</h2> <pre>{{ data.references }}</pre> {% endif %} <button onclick="window.print()">Print / Save as PDF</button> </div> """,
            data=data,
        )

    return render_page(
        "CV Builder",
        r""" <div class="card"> <h2>CV Builder</h2> <form method="post"> <label>Full Name</label> <input name="full_name" value="{{ user.name }}"> <label>Phone</label> <input name="phone" value="{{ user.phone or '' }}"> <label>Email</label> <input name="email" value="{{ user.email or '' }}"> <label>Address</label> <input name="address"> <label>Professional Profile</label> <textarea name="profile"></textarea> <label>Education</label> <textarea name="education"></textarea> <label>Work Experience</label> <textarea name="experience"></textarea> <label>Skills</label> <textarea name="skills"></textarea> <label>References</label> <textarea name="references"></textarea> <button type="submit">Generate CV</button> </form> <p class="muted"> Use Print / Save as PDF in the Android browser. No ReportLab package is required. </p> </div> """
    )


# ============================================================
# FARMER
# ============================================================

@app.route("/farmer", methods=["GET", "POST"])
@login_required
def farmer():
    user = current_user()

    if request.method == "POST":
        data = {
            "id": str(uuid.uuid4()),
            "user_id": user["id"],
            "nrc": clean(request.form.get("nrc")),
            "date_of_birth": (
                request.form.get("date_of_birth")
                or None
            ),
            "first_name": clean(
                request.form.get("first_name")
            ),
            "middle_names": clean(
                request.form.get("middle_names")
            ),
            "last_name": clean(
                request.form.get("last_name")
            ),
            "gender": clean(
                request.form.get("gender")
            ),
            "phone": clean(
                request.form.get("phone")
            ),
            "location": clean(
                request.form.get("location")
            ),
            "payment_method": clean(
                request.form.get("payment_method")
            ),
            "provider": clean(
                request.form.get("provider")
            ),
            "branch": clean(
                request.form.get("branch")
            ),
            "account_number": clean(
                request.form.get("account_number")
            ),
            "account_name": clean(
                request.form.get("account_name")
            ),
            "status": "submitted",
            "created_at": utc_now(),
        }

        f = request.files.get(
            "nrc_document"
        )

        if f and f.filename:
            uploaded, error = upload_storage(
                f,
                "farmer-nrc"
            )

            if error:
                flash(
                    error,
                    "danger"
                )
                return redirect(
                    url_for("farmer")
                )

            data["nrc_document_url"] = uploaded["url"]
            data["nrc_document_path"] = uploaded["path"]

        row, error = db_insert(
            "farmer_registrations",
            data
        )

        if error:
            minimal = {
                key: data[key]
                for key in (
                    "id",
                    "user_id",
                    "nrc",
                    "first_name",
                    "middle_names",
                    "last_name",
                    "gender",
                    "phone",
                    "location",
                )
                if key in data
            }

            row, error = db_insert(
                "farmer_registrations",
                minimal
            )

        if error:
            logger.error(
                "Farmer registration failed: %s",
                error
            )
            flash(
                "Farmer registration could not be submitted: "
                + str(error)[:1200],
                "danger"
            )
        else:
            flash(
                "Farmer registration submitted successfully.",
                "success"
            )
            log_activity(
                "farmer_registration",
                "Farmer registration submitted."
            )

        return redirect(
            url_for("farmer")
        )

    return render_page(
        "Farmer Registration",
        r""" <div class="card"> <h2>KOJA Farmer Registration</h2> <p>Register your agricultural service request.</p> <form method="post" enctype="multipart/form-data"> <h3>Personal Details</h3> <label>NRC</label> <input name="nrc"> <label>Date of Birth</label> <input type="date" name="date_of_birth"> <label>First Name</label> <input name="first_name"> <label>Middle Names</label> <input name="middle_names"> <label>Last Name</label> <input name="last_name"> <label>Gender</label> <select name="gender"> <option value="">Select</option> <option>Male</option> <option>Female</option> </select> <label>Phone</label> <input name="phone"> <label>NRC Card</label> <input type="file" name="nrc_document"> <h3>Farming Location</h3> <label>Location</label> <input name="location"> <h3>Payment Details</h3> <label>Payment Method</label> <select name="payment_method"> <option value="">Select</option> <option>Bank Account</option> <option>Mobile Money (MNO)</option> <option>Wallet</option> </select> <label>Provider</label> <input name="provider"> <label>Branch</label> <input name="branch"> <label>Account / Mobile Number</label> <input name="account_number"> <label>Account Name</label> <input name="account_name"> <button type="submit"> Submit Farmer Registration </button> </form> </div> """
    )


# ============================================================
# DOCTORS
# ============================================================

@app.route("/doctors")
@login_required
def doctors():
    doctors_rows = db_select(
        "doctor_profiles",
        order="created_at.desc",
        limit=100
    )

    return render_page(
        "Doctors",
        r""" <div class="card"> <h2>Find a Doctor</h2> <p>Choose a specific doctor and request an appointment.</p> </div> {% for d in doctors %} <div class="card"> <h3> {{ d.get("full_name") or d.get("doctor_name") or "Doctor" }} </h3> <p> <strong>Specialty:</strong> {{ d.get("specialty") or "General" }} </p> <p> <strong>Hospital/Clinic:</strong> {{ d.get("hospital_clinic") or "Not specified" }} </p> {% if d.get("consultation_fee") %} <p> <strong>Fee:</strong> {{ d.get("currency") or "ZMW" }} {{ d.get("consultation_fee") }} </p> {% endif %} <a class="btn" href="{{ url_for( 'book_doctor', provider_id=d.get('provider_id') ) }}"> Book This Doctor </a> </div> {% else %} <div class="card"> <p>No doctor profiles have been registered yet.</p> </div> {% endfor %} """,
        doctors=doctors_rows,
    )


@app.route( "/doctor/book/<provider_id>", methods=["GET", "POST"] )
@login_required
def book_doctor(provider_id):
    user = current_user()

    doctor = first_row(
        "doctor_profiles",
        {"provider_id": provider_id}
    )

    if not doctor:
        abort(404)

    if request.method == "POST":
        payload = {
            "id": str(uuid.uuid4()),
            "client_id": user["id"],
            "provider_id": provider_id,
            "appointment_type": "doctor",
            "appointment_date": request.form.get(
                "appointment_date"
            ),
            "start_time": request.form.get(
                "start_time"
            ),
            "end_time": request.form.get(
                "end_time"
            ),
            "location": clean(
                request.form.get("location")
            ),
            "status": "requested",
            "notes": clean(
                request.form.get("notes")
            ),
            "created_at": utc_now(),
            "updated_at": utc_now(),
        }

        row, error = db_insert(
            "appointments",
            payload
        )

        if error:
            flash(
                "Appointment could not be created: "
                + str(error)[:1000],
                "danger"
            )
        else:
            flash(
                "Doctor booking request submitted.",
                "success"
            )

        return redirect(
            url_for("dashboard")
        )

    return render_page(
        "Book Doctor",
        r""" <div class="card"> <h2> Book {{ doctor.get("full_name") or doctor.get("doctor_name") or "Doctor" }} </h2> <p> <strong>Specialty:</strong> {{ doctor.get("specialty") or "General" }} </p> <form method="post"> <label>Date</label> <input type="date" name="appointment_date" required> <label>Start Time</label> <input type="time" name="start_time"> <label>End Time</label> <input type="time" name="end_time"> <label>Location</label> <input name="location"> <label>Notes</label> <textarea name="notes"></textarea> <button type="submit"> Request Appointment </button> </form> </div> """,
        doctor=doctor,
    )


# ============================================================
# TEACHERS
# ============================================================

@app.route("/teachers")
@login_required
def teachers():
    teachers_rows = db_select(
        "teacher_profiles",
        order="created_at.desc",
        limit=100
    )

    return render_page(
        "Teachers",
        r""" <div class="card"> <h2>Find a Teacher / Tutor</h2> <p>Choose a teacher for tutoring.</p> </div> {% for t in teachers %} <div class="card"> <h3> {{ t.get("full_name") or t.get("teacher_name") or "Teacher" }} </h3> <p> <strong>Subjects:</strong> {{ t.get("subjects") or "Not specified" }} </p> <p> <strong>Grades:</strong> {{ t.get("grade_levels") or "Not specified" }} </p> <p> <strong>Qualification:</strong> {{ t.get("qualification") or "Not specified" }} </p> {% if t.get("hourly_rate") %} <p> <strong>Rate:</strong> {{ t.get("currency") or "ZMW" }} {{ t.get("hourly_rate") }}/hour </p> {% endif %} <a class="btn" href="{{ url_for( 'book_teacher', provider_id=t.get('provider_id') ) }}"> Book Teacher </a> </div> {% else %} <div class="card"> <p>No teacher profiles have been registered yet.</p> </div> {% endfor %} """,
        teachers=teachers_rows,
    )


@app.route( "/teacher/book/<provider_id>", methods=["GET", "POST"] )
@login_required
def book_teacher(provider_id):
    user = current_user()

    teacher = first_row(
        "teacher_profiles",
        {"provider_id": provider_id}
    )

    if not teacher:
        abort(404)

    if request.method == "POST":
        payload = {
            "id": str(uuid.uuid4()),
            "client_id": user["id"],
            "provider_id": provider_id,
            "appointment_type": "teacher",
            "appointment_date": request.form.get(
                "appointment_date"
            ),
            "start_time": request.form.get(
                "start_time"
            ),
            "end_time": request.form.get(
                "end_time"
            ),
            "location": clean(
                request.form.get("location")
            ),
            "status": "requested",
            "notes": clean(
                request.form.get("notes")
            ),
            "created_at": utc_now(),
            "updated_at": utc_now(),
        }

        row, error = db_insert(
            "appointments",
            payload
        )

        if error:
            flash(
                "Teacher booking failed: "
                + str(error)[:1000],
                "danger"
            )
        else:
            flash(
                "Teacher booking request submitted.",
                "success"
            )

        return redirect(
            url_for("dashboard")
        )

    return render_page(
        "Book Teacher",
        r""" <div class="card"> <h2> Book {{ teacher.get("full_name") or teacher.get("teacher_name") or "Teacher" }} </h2> <p> {{ teacher.get("subjects") or "" }} </p> <form method="post"> <label>Date</label> <input type="date" name="appointment_date" required> <label>Start Time</label> <input type="time" name="start_time"> <label>End Time</label> <input type="time" name="end_time"> <label>Location / Online</label> <input name="location"> <label>Notes</label> <textarea name="notes"></textarea> <button type="submit"> Book Teacher </button> </form> </div> """,
        teacher=teacher,
    )


# ============================================================
# DRIVER REGISTRATION
# ============================================================

DRIVER_PROFILE_COLUMNS = (
    "id,provider_id,vehicle_type,vehicle_make,vehicle_model,"
    "vehicle_registration,driving_license_number,service_area,"
    "verification_status,created_at"
)


@app.route( "/driver/register", methods=["GET", "POST"] )
@app.route( "/drivers/register", methods=["GET", "POST"] )
@login_required
def driver_register():
    user = current_user()

    provider = get_driver_provider(
        user.get("id")
    )

    existing = None

    if provider:
        existing = first_row(
            "driver_profiles",
            {
                "provider_id": provider.get("id")
            }
        )

    if request.method == "POST":
        vehicle_type = clean(
            request.form.get("vehicle_type")
        )
        vehicle_make = clean(
            request.form.get("vehicle_make")
        )
        vehicle_model = clean(
            request.form.get("vehicle_model")
        )
        vehicle_registration = clean(
            request.form.get("vehicle_registration")
        )
        driving_license_number = clean(
            request.form.get("driving_license_number")
        )
        service_area = clean(
            request.form.get("service_area")
        )

        if (
            not vehicle_type
            or not vehicle_registration
            or not driving_license_number
        ):
            flash(
                "Vehicle type, vehicle registration and "
                "driving licence number are required.",
                "danger"
            )
            return redirect(
                url_for("driver_register")
            )

        if not table_exists("service_providers"):
            flash(
                "The service_providers table is missing.",
                "danger"
            )
            return redirect(
                url_for("driver_register")
            )

        if not table_exists("driver_profiles"):
            flash(
                "The driver_profiles table is missing.",
                "danger"
            )
            return redirect(
                url_for("driver_register")
            )

        provider, provider_error = ensure_driver_provider(
            user
        )

        if (
            provider_error
            or not provider
            or not provider.get("id")
        ):
            logger.error(
                "Driver provider creation failed: %s",
                provider_error
            )
            flash(
                "Driver registration failed while creating "
                "the service provider record: "
                + str(
                    provider_error
                    or "Unknown database error"
                )[:1200],
                "danger"
            )
            return redirect(
                url_for("driver_register")
            )

        provider_id = str(
            provider["id"]
        )

        existing = first_row(
            "driver_profiles",
            {"provider_id": provider_id}
        )

        # EXACT confirmed driver_profiles columns.
        payload = {
            "provider_id": provider_id,
            "vehicle_type": vehicle_type,
            "vehicle_make": vehicle_make or None,
            "vehicle_model": vehicle_model or None,
            "vehicle_registration": vehicle_registration,
            "driving_license_number":
                driving_license_number,
            "service_area": service_area or None,
            "verification_status": "pending",
        }

        if existing and existing.get("id"):
            row, error = db_update(
                "driver_profiles",
                {"id": existing["id"]},
                payload
            )
        else:
            payload["id"] = str(uuid.uuid4())

            row, error = db_insert(
                "driver_profiles",
                payload
            )

        if error:
            logger.error(
                "Driver profile insert/update failed: %s",
                error
            )
            flash(
                "Driver registration failed: "
                + str(error)[:1400],
                "danger"
            )
            return redirect(
                url_for("driver_register")
            )

        # Update the profile role when possible.
        if table_exists("profiles"):
            db_update(
                "profiles",
                {"id": user["id"]},
                {"role": "driver"}
            )

        session["user"]["role"] = "driver"
        session["user"]["driver_provider_id"] = provider_id
        session["user"]["vehicle_type"] = vehicle_type
        session["user"]["vehicle_registration"] = (
            vehicle_registration
        )
        session["user"]["driving_license_number"] = (
            driving_license_number
        )

        log_activity(
            "driver_registration",
            "Driver profile submitted for verification."
        )

        flash(
            "Driver registration submitted successfully. "
            "Your profile is pending admin verification.",
            "success"
        )

        return redirect(
            url_for("driver_dashboard")
        )

    return render_page(
        "Driver Registration",
        r""" <div class="card"> <h2>Driver Registration</h2> <p> Complete your driver and vehicle information. A KOJA administrator must verify your registration before customers can request you. </p> <form method="post"> <label>Vehicle Type</label> <select name="vehicle_type" required> <option value="">Select vehicle type</option> <option>Motorcycle</option> <option>Car</option> <option>Van</option> <option>Pickup</option> <option>Truck</option> <option>Bicycle</option> </select> <label>Vehicle Make</label> <input name="vehicle_make"> <label>Vehicle Model</label> <input name="vehicle_model"> <label>Vehicle Registration</label> <input name="vehicle_registration" required> <label>Driving Licence Number</label> <input name="driving_license_number" required> <label>Service Area</label> <input name="service_area"> <button type="submit"> Submit Driver Registration </button> </form> {% if existing %} <p> Current verification status: <strong> {{ existing.get("verification_status") or "pending" }} </strong> </p> {% endif %} </div> """,
        existing=existing,
    )


# ============================================================
# DRIVER DASHBOARD
# ============================================================

@app.route("/driver")
@login_required
def driver_dashboard():
    user = current_user()

    provider = get_driver_provider(
        user.get("id")
    )

    if not provider:
        return redirect(
            url_for("driver_register")
        )

    profile = first_row(
        "driver_profiles",
        {"provider_id": provider.get("id")}
    )

    if not profile:
        return redirect(
            url_for("driver_register")
        )

    provider_id = str(
        provider.get("id")
    )

    locations = db_select(
        "driver_locations",
        filters={"driver_id": provider_id},
        order="created_at.desc",
        limit=1
    )

    latest = locations[0] if locations else None

    requests_rows = db_select(
        "deliveries",
        filters={"driver_id": provider_id},
        order="created_at.desc",
        limit=100
    )

    return render_page(
        "Driver Dashboard",
        r""" <div class="card"> <h2>Driver Dashboard</h2> <p> <strong>{{ user.name }}</strong> — {{ profile.get("vehicle_type") or "Vehicle" }} {{ profile.get("vehicle_registration") or "" }} </p> <p> Verification: <strong> {{ profile.get("verification_status") or "pending" }} </strong> </p> </div> <div class="card"> <h3>GPS / Availability</h3> <p> Current status: <strong> {{ "ONLINE" if latest and latest.get("is_online") else "OFFLINE" }} </strong> </p> <a class="btn" href="{{ url_for('tracking') }}"> Open GPS & Go Online </a> </div> <div class="card"> <h3>Delivery Requests / Jobs</h3> {% for d in requests_rows %} <div class="card"> <strong>{{ d.get("tracking_code") }}</strong> <p> {{ d.get("pickup_location") }} → {{ d.get("destination") }} </p> <p> Status: <strong>{{ d.get("status") or "requested" }}</strong> </p> {% if d.get("status") == "requested" %} <form method="post" action="{{ url_for( 'driver_delivery_action', delivery_id=d.get('id'), action='accept' ) }}"> <button type="submit">Accept</button> </form> <form method="post" action="{{ url_for( 'driver_delivery_action', delivery_id=d.get('id'), action='reject' ) }}"> <button type="submit">Reject</button> </form> {% elif d.get("status") == "accepted" %} <form method="post" action="{{ url_for( 'driver_delivery_action', delivery_id=d.get('id'), action='picked_up' ) }}"> <button type="submit">Picked Up</button> </form> {% elif d.get("status") == "picked_up" %} <form method="post" action="{{ url_for( 'driver_delivery_action', delivery_id=d.get('id'), action='in_transit' ) }}"> <button type="submit">In Transit</button> </form> {% elif d.get("status") == "in_transit" %} <form method="post" action="{{ url_for( 'driver_delivery_action', delivery_id=d.get('id'), action='delivered' ) }}"> <button type="submit">Delivered</button> </form> {% endif %} {% if d.get("tracking_code") %} <a class="btn" href="{{ url_for( 'track_delivery', tracking_code=d.get('tracking_code') ) }}"> Track Map </a> {% endif %} </div> {% else %} <p>No delivery requests yet.</p> {% endfor %} </div> """,
        profile=profile,
        latest=latest,
        requests_rows=requests_rows,
    )


@app.route( "/driver/delivery/<delivery_id>/<action>", methods=["POST"] )
@driver_required
def driver_delivery_action( delivery_id, action ):
    user = current_user()

    provider = get_driver_provider(
        user.get("id")
    )

    if not provider:
        flash(
            "Driver provider record not found.",
            "danger"
        )
        return redirect(
            url_for("driver_register")
        )

    provider_id = str(
        provider["id"]
    )

    delivery = first_row(
        "deliveries",
        {"id": delivery_id}
    )

    if not delivery:
        abort(404)

    if action in ("accept", "reject"):
        assigned = delivery.get(
            "driver_id"
        )

        if (
            assigned
            and str(assigned) != provider_id
        ):
            flash(
                "This delivery is assigned to another driver.",
                "danger"
            )
            return redirect(
                url_for("driver_dashboard")
            )

    statuses = {
        "accept": "accepted",
        "reject": "rejected",
        "picked_up": "picked_up",
        "in_transit": "in_transit",
        "delivered": "delivered",
    }

    if action not in statuses:
        abort(400)

    status = statuses[action]

    payload = {
        "status": status,
        "updated_at": utc_now(),
    }

    if action == "accept":
        payload["driver_id"] = provider_id

    row, error = db_update(
        "deliveries",
        {"id": delivery_id},
        payload
    )

    if error:
        flash(
            "Could not update delivery status: "
            + str(error)[:1000],
            "danger"
        )
    else:
        log_activity(
            "delivery_status",
            f"Delivery {delivery.get('tracking_code')} "
            f"changed to {status}."
        )
        flash(
            f"Delivery status changed to {status}.",
            "success"
        )

    return redirect(
        url_for("driver_dashboard")
    )


# ============================================================
# DRIVER GPS
# ============================================================

@app.route("/tracking")
@login_required
def tracking():
    return render_page(
        "Live GPS Tracking",
        r""" <div class="card"> <h2>Live Driver GPS</h2> <p> Allow browser location permission. Keep this page open while driving. </p> <label>Delivery ID (optional)</label> <input id="deliveryId" placeholder="Optional delivery ID"> <button onclick="startGPS()"> Go Online / Start GPS </button> <button onclick="stopGPS()"> Stop GPS / Go Offline </button> <p id="status">GPS not started.</p> <pre id="coords"></pre> </div> <script> let watchId = null; function show(text) { document.getElementById("status").textContent = text; } function startGPS() { if (!navigator.geolocation) { show("This browser does not support GPS."); return; } if (watchId !== null) { show("GPS is already running."); return; } show("Requesting location permission..."); watchId = navigator.geolocation.watchPosition( async function(position) { const c = position.coords; document.getElementById("coords").textContent = "Latitude: " + c.latitude + "\\n" + "Longitude: " + c.longitude + "\\n" + "Accuracy: " + c.accuracy + " m"; const payload = { latitude: c.latitude, longitude: c.longitude, accuracy: c.accuracy, speed: c.speed, heading: c.heading, delivery_id: document.getElementById("deliveryId").value }; try { const response = await fetch( "{{ url_for('driver_location_update') }}", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) } ); const data = await response.json(); if (data.ok) { show( "ONLINE — GPS updated at " + new Date().toLocaleTimeString() ); } else { show(data.message || "GPS update failed."); } } catch (e) { show("Network error while sending GPS."); } }, function(error) { show( "GPS error: " + error.message ); }, { enableHighAccuracy: true, maximumAge: 5000, timeout: 20000 } ); } async function stopGPS() { if (watchId !== null) { navigator.geolocation.clearWatch(watchId); watchId = null; } try { await fetch( "{{ url_for('driver_offline') }}", { method: "POST" } ); } catch (e) {} show("OFFLINE"); } </script> """
    )


@app.route( "/api/driver/location", methods=["POST"] )
@driver_required
def driver_location_update():
    if not table_exists("driver_locations"):
        return jsonify({
            "ok": False,
            "message": (
                "driver_locations table is not available."
            )
        }), 503

    user = current_user()

    provider = get_driver_provider(
        user.get("id")
    )

    if not provider:
        return jsonify({
            "ok": False,
            "message": "Driver provider profile not found."
        }), 404

    provider_id = str(
        provider["id"]
    )

    body = request.get_json(
        silent=True
    ) or {}

    lat = safe_float(
        body.get("latitude")
    )
    lon = safe_float(
        body.get("longitude")
    )

    if (
        lat is None
        or lon is None
        or not (-90 <= lat <= 90)
        or not (-180 <= lon <= 180)
    ):
        return jsonify({
            "ok": False,
            "message": (
                "Invalid latitude or longitude."
            )
        }), 400

    payload = {
        "id": str(uuid.uuid4()),
        "driver_id": provider_id,
        "latitude": lat,
        "longitude": lon,
        "accuracy": safe_float(
            body.get("accuracy")
        ),
        "speed": safe_float(
            body.get("speed")
        ),
        "heading": safe_float(
            body.get("heading")
        ),
        "is_online": True,
        "created_at": utc_now(),
    }

    row, error = db_insert(
        "driver_locations",
        payload
    )

    if error:
        logger.error(
            "driver_locations insert failed: %s",
            error
        )
        return jsonify({
            "ok": False,
            "message": (
                "GPS location could not be saved."
            ),
            "error": str(error)[:1000],
        }), 500

    delivery_id = clean(
        body.get("delivery_id")
    )

    if delivery_id and table_exists("deliveries"):
        delivery = first_row(
            "deliveries",
            {"id": delivery_id}
        )

        if delivery:
            assigned = str(
                delivery.get("driver_id") or ""
            )

            if assigned in ("", provider_id):
                db_update(
                    "deliveries",
                    {"id": delivery_id},
                    {
                        "driver_id": provider_id,
                        "updated_at": utc_now(),
                    }
                )

    return jsonify({
        "ok": True,
        "latitude": lat,
        "longitude": lon,
        "created_at": utc_now(),
    })


@app.route( "/api/driver/offline", methods=["POST"] )
@driver_required
def driver_offline():
    if not table_exists("driver_locations"):
        return jsonify({
            "ok": False,
            "message": (
                "driver_locations table is not available."
            )
        }), 503

    user = current_user()

    provider = get_driver_provider(
        user.get("id")
    )

    if not provider:
        return jsonify({
            "ok": False,
            "message": (
                "Driver provider profile not found."
            )
        }), 404

    provider_id = str(
        provider["id"]
    )

    latest_rows = db_select(
        "driver_locations",
        filters={"driver_id": provider_id},
        order="created_at.desc",
        limit=1
    )

    latest = latest_rows[0] if latest_rows else None

    payload = {
        "id": str(uuid.uuid4()),
        "driver_id": provider_id,
        "latitude": (
            latest.get("latitude")
            if latest else None
        ),
        "longitude": (
            latest.get("longitude")
            if latest else None
        ),
        "accuracy": (
            latest.get("accuracy")
            if latest else None
        ),
        "speed": None,
        "heading": None,
        "is_online": False,
        "created_at": utc_now(),
    }

    row, error = db_insert(
        "driver_locations",
        payload
    )

    if error:
        return jsonify({
            "ok": False,
            "message": (
                "Could not mark driver offline."
            ),
            "error": str(error)[:1000],
        }), 500

    return jsonify({
        "ok": True,
        "message": "Driver is now offline."
    })


# ============================================================
# NEARBY DRIVERS
# ============================================================

@app.route("/drivers")
@login_required
def drivers():
    return render_page(
        "Nearby Drivers",
        r""" <div class="card"> <h2>Nearby Delivery Drivers</h2> <p> Share your pickup/shop location and KOJA will calculate distances to online drivers. </p> <label>Your Latitude</label> <input id="latitude"> <label>Your Longitude</label> <input id="longitude"> <button onclick="useMyLocation()"> Use My Current Location </button> <button onclick="findDrivers()"> Find Nearby Drivers </button> <div id="results"></div> </div> <script> function useMyLocation() { navigator.geolocation.getCurrentPosition( function(position) { document.getElementById("latitude").value = position.coords.latitude; document.getElementById("longitude").value = position.coords.longitude; }, function(error) { alert("Location error: " + error.message); }, { enableHighAccuracy: true, timeout: 20000 } ); } async function findDrivers() { const lat = document.getElementById("latitude").value; const lon = document.getElementById("longitude").value; if (!lat || !lon) { alert("Enter or detect your location first."); return; } const response = await fetch( "{{ url_for('nearby_drivers') }}" + "?latitude=" + encodeURIComponent(lat) + "&longitude=" + encodeURIComponent(lon) ); const data = await response.json(); if (!data.ok) { document.getElementById("results").innerHTML = "<div class='danger'>" + data.message + "</div>"; return; } if (!data.drivers.length) { document.getElementById("results").innerHTML = "<div class='card'>" + "No online drivers found nearby." + "</div>"; return; } let html = "<h3>Available Drivers</h3>"; data.drivers.forEach(function(d) { html += "<div class='card'>" + "<h3>" + escapeHtml(d.name) + "</h3>" + "<p>Vehicle: " + escapeHtml(d.vehicle_type || "") + "</p>" + "<p>Registration: " + escapeHtml(d.vehicle_registration || "") + "</p>" + "<p>Distance: " + d.distance_km + " km</p>" + "<button onclick='sendRequest(" + JSON.stringify(d.driver_id) + ")'>" + "Send Delivery Request" + "</button>" + "</div>"; }); document.getElementById("results").innerHTML = html; } async function sendRequest(driverId) { const pickup = prompt("Pickup / shop location:"); if (!pickup) return; const destination = prompt("Destination:"); if (!destination) return; const recipientName = prompt("Recipient name:"); const recipientPhone = prompt("Recipient phone:"); const packageDescription = prompt("Package description:"); const lat = document.getElementById("latitude").value; const lon = document.getElementById("longitude").value; const response = await fetch( "{{ url_for('create_delivery_request') }}", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ driver_id: driverId, pickup_location: pickup, destination: destination, pickup_latitude: lat, pickup_longitude: lon, recipient_name: recipientName, recipient_phone: recipientPhone, package_description: packageDescription, delivery_fee: 0 }) } ); const data = await response.json(); if (data.ok) { alert(data.message); window.location.href = "{{ url_for('deliveries') }}"; } else { alert( data.message || "Delivery request failed." ); } } function escapeHtml(value) { return String(value || "") .replace(/&/g, "&amp;") .replace(/</g, "&lt;") .replace(/>/g, "&gt;") .replace(/"/g, "&quot;") .replace(/'/g, "&#039;"); } </script> """
    )


@app.route("/api/nearby-drivers")
@login_required
def nearby_drivers():
    lat = safe_float(
        request.args.get("latitude")
    )
    lon = safe_float(
        request.args.get("longitude")
    )

    radius = safe_float(
        request.args.get("radius_km")
    ) or 50

    radius = max(
        1,
        min(radius, 200)
    )

    if (
        lat is None
        or lon is None
        or not (-90 <= lat <= 90)
        or not (-180 <= lon <= 180)
    ):
        return jsonify({
            "ok": False,
            "message": (
                "Valid latitude and longitude are required."
            )
        }), 400

    if not table_exists("driver_locations"):
        return jsonify({
            "ok": False,
            "message": (
                "The driver_locations table is not installed."
            )
        }), 503

    latest = latest_driver_locations()
    results = []

    now = datetime.now(timezone.utc)

    for driver_id, loc in latest.items():
        if not loc.get("is_online"):
            continue

        dlat = safe_float(
            loc.get("latitude")
        )
        dlon = safe_float(
            loc.get("longitude")
        )

        if dlat is None or dlon is None:
            continue

        created = loc.get(
            "created_at"
        )

        # Do not show stale drivers older than 10 minutes.
        if created:
            try:
                dt = datetime.fromisoformat(
                    str(created).replace(
                        "Z",
                        "+00:00"
                    )
                )

                if (
                    now - dt
                ).total_seconds() > 600:
                    continue

            except Exception:
                pass

        distance = haversine_km(
            lat,
            lon,
            dlat,
            dlon
        )

        if distance > radius:
            continue

        profile = first_row(
            "driver_profiles",
            {"provider_id": driver_id}
        )

        provider = first_row(
            "service_providers",
            {"id": driver_id}
        ) or {}

        results.append({
            "driver_id": str(driver_id),
            "name": first_nonempty(
                provider.get("full_name"),
                provider.get("name"),
                "Driver",
            ),
            "phone": first_nonempty(
                provider.get("phone")
            ),
            "vehicle_type": first_nonempty(
                profile.get("vehicle_type")
                if profile else ""
            ),
            "vehicle_registration": first_nonempty(
                profile.get("vehicle_registration")
                if profile else ""
            ),
            "latitude": dlat,
            "longitude": dlon,
            "accuracy": loc.get(
                "accuracy"
            ),
            "distance_km": round(
                distance,
                2
            ),
            "updated_at": loc.get(
                "created_at"
            ),
        })

    results.sort(
        key=lambda x: x["distance_km"]
    )

    return jsonify({
        "ok": True,
        "drivers": results
    })


# ============================================================
# DELIVERY REQUESTS / TRACKING
# ============================================================

def make_tracking_code():
    return (
        "KOJA-"
        + datetime.now().strftime("%Y%m%d")
        + "-"
        + secrets.token_hex(3).upper()
    )


@app.route( "/api/delivery/request", methods=["POST"] )
@login_required
def create_delivery_request():
    user = current_user()

    body = request.get_json(
        silent=True
    ) or {}

    driver_id = clean(
        body.get("driver_id")
    )

    if not driver_id:
        return jsonify({
            "ok": False,
            "message": "Select a driver first."
        }), 400

    driver = first_row(
        "driver_profiles",
        {"provider_id": driver_id}
    )

    if not driver:
        return jsonify({
            "ok": False,
            "message": "Driver profile not found."
        }), 404

    lat = safe_float(
        body.get("pickup_latitude")
    )

    lon = safe_float(
        body.get("pickup_longitude")
    )

    tracking = make_tracking_code()

    payload = {
        "id": str(uuid.uuid4()),
        "customer_id": user["id"],
        "user_id": user["id"],
        "driver_id": driver_id,
        "pickup_location": clean(
            body.get("pickup_location")
        ),
        "destination": clean(
            body.get("destination")
        ),
        "pickup_latitude": lat,
        "pickup_longitude": lon,
        "recipient_name": clean(
            body.get("recipient_name")
        ),
        "recipient_phone": clean(
            body.get("recipient_phone")
        ),
        "package_description": clean(
            body.get("package_description")
        ),
        "package_weight": body.get(
            "package_weight"
        ),
        "delivery_fee": body.get(
            "delivery_fee"
        ) or 0,
        "currency": "ZMW",
        "status": "requested",
        "tracking_code": tracking,
        "notes": clean(
            body.get("notes")
        ),
        "created_at": utc_now(),
        "updated_at": utc_now(),
    }

    row, error = db_insert(
        "deliveries",
        payload
    )

    if error:
        minimal = {
            "id": payload["id"],
            "customer_id": user["id"],
            "driver_id": driver_id,
            "pickup_location":
                payload["pickup_location"],
            "destination":
                payload["destination"],
            "recipient_name":
                payload["recipient_name"],
            "recipient_phone":
                payload["recipient_phone"],
            "package_description":
                payload["package_description"],
            "status": "requested",
            "tracking_code": tracking,
        }

        row, error = db_insert(
            "deliveries",
            minimal
        )

    if error:
        return jsonify({
            "ok": False,
            "message": (
                "Delivery request could not be created."
            ),
            "error": str(error)[:1200],
        }), 500

    log_activity(
        "delivery_requested",
        f"Delivery {tracking} requested "
        f"from driver {driver_id}."
    )

    return jsonify({
        "ok": True,
        "tracking_code": tracking,
        "message": (
            "Delivery request sent to the driver. "
            f"Tracking code: {tracking}."
        ),
    })


@app.route( "/deliveries", methods=["GET", "POST"] )
@login_required
def deliveries():
    user = current_user()

    if request.method == "POST":
        tracking = make_tracking_code()

        payload = {
            "id": str(uuid.uuid4()),
            "customer_id": user["id"],
            "pickup_location": clean(
                request.form.get(
                    "pickup_location"
                )
            ),
            "destination": clean(
                request.form.get(
                    "destination"
                )
            ),
            "recipient_name": clean(
                request.form.get(
                    "recipient_name"
                )
            ),
            "recipient_phone": clean(
                request.form.get(
                    "recipient_phone"
                )
            ),
            "package_description": clean(
                request.form.get(
                    "package_description"
                )
            ),
            "package_weight": (
                request.form.get(
                    "package_weight"
                ) or None
            ),
            "delivery_fee": (
                request.form.get(
                    "delivery_fee"
                ) or 0
            ),
            "currency": "ZMW",
            "requested_date": (
                request.form.get(
                    "requested_date"
                ) or None
            ),
            "requested_time": (
                request.form.get(
                    "requested_time"
                ) or None
            ),
            "status": "requested",
            "tracking_code": tracking,
            "notes": clean(
                request.form.get("notes")
            ),
            "created_at": utc_now(),
            "updated_at": utc_now(),
        }

        row, error = db_insert(
            "deliveries",
            payload
        )

        if error:
            flash(
                "Delivery could not be registered: "
                + str(error)[:1000],
                "danger"
            )
        else:
            flash(
                f"Delivery registered. "
                f"Tracking code: {tracking}. "
                "Now choose a nearby driver.",
                "success"
            )
            return redirect(
                url_for("drivers")
            )

        return redirect(
            url_for("deliveries")
        )

    rows = db_select(
        "deliveries",
        filters={
            "customer_id": user["id"]
        },
        order="created_at.desc",
        limit=100
    )

    return render_page(
        "Deliveries",
        r""" <div class="card"> <h2>Delivery Service</h2> <p> Use Nearby Drivers to see drivers around your shop/pickup location. </p> <a class="btn" href="{{ url_for('drivers') }}"> Find Nearby Drivers </a> </div> <div class="card"> <h2>Create Delivery Without Selecting Driver Yet</h2> <form method="post"> <label>Pickup / Shop Location</label> <input name="pickup_location"> <label>Destination</label> <input name="destination"> <label>Recipient Name</label> <input name="recipient_name"> <label>Recipient Phone</label> <input name="recipient_phone"> <label>Package Description</label> <input name="package_description"> <label>Package Weight (kg)</label> <input name="package_weight"> <label>Delivery Fee (ZMW)</label> <input name="delivery_fee"> <label>Requested Date</label> <input type="date" name="requested_date"> <label>Requested Time</label> <input type="time" name="requested_time"> <label>Notes</label> <textarea name="notes"></textarea> <button type="submit"> Create Delivery Request </button> </form> </div> <div class="card"> <h2>My Deliveries</h2> {% for d in rows %} <div class="card"> <strong>{{ d.get("tracking_code") }}</strong> <p> {{ d.get("pickup_location") }} → {{ d.get("destination") }} </p> <p> Status: <strong>{{ d.get("status") or "requested" }}</strong> </p> <p> Driver: {{ d.get("driver_id") or "Not selected" }} </p> <a class="btn" href="{{ url_for( 'track_delivery', tracking_code=d.get('tracking_code') ) }}"> Track Delivery </a> {% if not d.get("driver_id") %} <a class="btn" href="{{ url_for('drivers') }}"> Find Driver </a> {% endif %} </div> {% else %} <p>No deliveries registered.</p> {% endfor %} </div> """,
        rows=rows,
    )


@app.route( "/track/<tracking_code>" )
@login_required
def track_delivery(tracking_code):
    delivery = first_row(
        "deliveries",
        {"tracking_code": tracking_code}
    )

    if not delivery:
        abort(404)

    return render_page(
        "Track Delivery",
        r""" <div class="card"> <h2>Delivery Tracking</h2> <p> Tracking code: <strong>{{ delivery.get("tracking_code") }}</strong> </p> <p> <strong>Pickup:</strong> {{ delivery.get("pickup_location") }} </p> <p> <strong>Destination:</strong> {{ delivery.get("destination") }} </p> <p> <strong>Status:</strong> <span id="status"> {{ delivery.get("status") }} </span> </p> <div id="location"> Waiting for driver's location... </div> </div> <script> async function updateLocation() { try { const response = await fetch( "{{ url_for( 'delivery_location', tracking_code=delivery.get('tracking_code') ) }}" ); const data = await response.json(); if (data.ok) { document.getElementById("status") .textContent = data.status || ""; document.getElementById("location") .innerHTML = "<p>Latitude: " + data.latitude + "</p>" + "<p>Longitude: " + data.longitude + "</p>" + "<p>Last update: " + data.updated_at + "</p>"; } } catch (e) {} } updateLocation(); setInterval(updateLocation, 10000); </script> """,
        delivery=delivery,
    )


@app.route( "/api/delivery/<tracking_code>/location" )
@login_required
def delivery_location(tracking_code):
    delivery = first_row(
        "deliveries",
        {"tracking_code": tracking_code}
    )

    if not delivery:
        return jsonify({
            "ok": False,
            "message": "Delivery not found."
        }), 404

    driver_id = delivery.get(
        "driver_id"
    )

    locations = []

    if driver_id:
        locations = db_select(
            "driver_locations",
            filters={
                "driver_id": driver_id
            },
            order="created_at.desc",
            limit=1
        )

    if not locations:
        return jsonify({
            "ok": False,
            "message": (
                "Driver has not shared a GPS location yet."
            ),
            "status": delivery.get(
                "status"
            ),
        })

    loc = locations[0]

    return jsonify({
        "ok": True,
        "latitude": loc.get("latitude"),
        "longitude": loc.get("longitude"),
        "accuracy": loc.get("accuracy"),
        "speed": loc.get("speed"),
        "heading": loc.get("heading"),
        "updated_at": loc.get("created_at"),
        "status": delivery.get("status"),
    })


# ============================================================
# PROVIDER LOCATION
# ============================================================

@app.route( "/provider-map/<provider_id>" )
@login_required
def provider_map(provider_id):
    provider_type = request.args.get(
        "provider_type",
        "provider"
    )

    return render_page(
        "Provider Location",
        r""" <div class="card"> <h2> {{ provider_type|title }} Location </h2> <p> Latest GPS position shared by this provider. </p> <div id="location"> Loading provider location... </div> </div> <script> async function loadLocation() { try { const response = await fetch( "{{ url_for( 'provider_location', provider_id=provider_id ) }}" ); const data = await response.json(); if (data.ok) { document.getElementById("location") .innerHTML = "<p>Latitude: " + data.latitude + "</p>" + "<p>Longitude: " + data.longitude + "</p>" + "<p>Updated: " + data.updated_at + "</p>"; } else { document.getElementById("location") .textContent = data.message || "No location."; } } catch (e) { document.getElementById("location") .textContent = "Could not load provider location."; } } loadLocation(); setInterval(loadLocation, 10000); </script> """,
        provider_id=provider_id,
        provider_type=provider_type,
    )


@app.route( "/api/provider/<provider_id>/location" )
@login_required
def provider_location(provider_id):
    rows = db_select(
        "driver_locations",
        filters={
            "driver_id": provider_id
        },
        order="created_at.desc",
        limit=1
    )

    if not rows:
        return jsonify({
            "ok": False,
            "message": (
                "This provider has not shared "
                "a GPS location."
            )
        })

    loc = rows[0]

    return jsonify({
        "ok": True,
        "latitude": loc.get("latitude"),
        "longitude": loc.get("longitude"),
        "accuracy": loc.get("accuracy"),
        "updated_at": loc.get("created_at"),
    })


# ============================================================
# UNIVERSITIES
# ============================================================

@app.route("/universities")
@login_required
def universities():
    universities_rows = db_select(
        "universities",
        order="name.asc",
        limit=200
    )

    return render_page(
        "Universities",
        r""" <div class="card"> <h2>University Applications</h2> <p> Select the university, programme, intake/year and review requirements. </p> </div> {% if universities %} {% for university in universities %} <div class="card"> <h3> {{ university.get("name") or university.get("university_name") or "University" }} </h3> <p> {{ university.get("location") or university.get("description") or "" }} </p> <a class="btn" href="{{ url_for( 'university_apply', university_id=university.get('id') ) }}"> Apply </a> </div> {% endfor %} {% else %} <div class="card"> <p> No universities are currently loaded into the universities table. </p> </div> {% endif %} """,
        universities=universities_rows,
    )


@app.route( "/university/apply/<university_id>", methods=["GET", "POST"] )
@login_required
def university_apply(university_id):
    user = current_user()

    university = first_row(
        "universities",
        {"id": university_id}
    )

    if not university:
        abort(404)

    programmes = db_select(
        "university_programmes",
        filters={
            "university_id": university_id
        },
        order="name.asc",
        limit=500
    )

    requirements = db_select(
        "university_application_requirements",
        filters={
            "university_id": university_id
        },
        limit=500
    )

    if request.method == "POST":
        programme_id = request.form.get(
            "programme_id"
        )
        year = request.form.get(
            "academic_year"
        )
        intake = clean(
            request.form.get("intake")
        )

        payload = {
            "id": str(uuid.uuid4()),
            "user_id": user["id"],
            "university_id": university_id,
            "programme_id": programme_id,
            "academic_year": year,
            "intake": intake or None,
            "full_name": user["name"],
            "email": user["email"],
            "phone": user.get("phone"),
            "status": "draft",
            "created_at": utc_now(),
        }

        row, error = db_insert(
            "university_applications",
            payload
        )

        if error:
            minimal = {
                key: payload[key]
                for key in (
                    "id",
                    "user_id",
                    "university_id",
                    "programme_id",
                    "academic_year",
                )
            }

            row, error = db_insert(
                "university_applications",
                minimal
            )

        if error:
            flash(
                "Application could not be created: "
                + str(error)[:1000],
                "danger"
            )
        else:
            flash(
                "University application started successfully.",
                "success"
            )

        return redirect(
            url_for("universities")
        )

    return render_page(
        "University Application",
        r""" <div class="card"> <h2> {{ university.get("name") or university.get("university_name") }} </h2> <form method="post"> <label>Programme</label> <select name="programme_id"> <option value="">Select programme</option> {% for p in programmes %} <option value="{{ p.get('id') }}"> {{ p.get("name") or p.get("programme_name") or p.get("title") }} </option> {% endfor %} </select> <label>Academic Year</label> <select name="academic_year"> <option>2026/2027</option> <option>2027/2028</option> <option>2028/2029</option> </select> <label>Intake</label> <select name="intake"> <option>January</option> <option>May</option> <option>September</option> <option>Other</option> </select> <button type="submit"> Start Application </button> </form> </div> <div class="card"> <h3>Application Requirements</h3> {% for r in requirements %} <div class="card"> <strong> {{ r.get("title") or r.get("requirement") or "Requirement" }} </strong> <p> {{ r.get("description") or r.get("details") or "" }} </p> </div> {% else %} <p> No specific requirements have been entered for this university yet. </p> {% endfor %} </div> """,
        university=university,
        programmes=programmes,
        requirements=requirements,
    )


# ============================================================
# ADMIN
# ============================================================

@app.route("/admin")
@admin_required
def admin():
    tables = [
        "profiles",
        "questions",
        "assignments",
        "farmer_registrations",
        "doctor_profiles",
        "teacher_profiles",
        "driver_profiles",
        "driver_locations",
        "deliveries",
        "appointments",
        "universities",
        "university_applications",
        "activity_logs",
    ]

    counts = {}

    for table in tables:
        counts[table] = len(
            db_select(
                table,
                limit=1000
            )
        )

    return render_page(
        "Admin Dashboard",
        r""" <div class="card"> <h2>KOJA Administrator</h2> <p>System management dashboard.</p> </div> <div class="grid"> {% for name, count in counts.items() %} <div class="card"> <div class="stat">{{ count }}</div> <p>{{ name }}</p> </div> {% endfor %} </div> <div class="card"> <h3>Management</h3> <a class="btn" href="{{ url_for('admin_users') }}"> Users </a> <a class="btn" href="{{ url_for('admin_drivers') }}"> Drivers </a> <a class="btn" href="{{ url_for('admin_deliveries') }}"> Deliveries </a> <a class="btn" href="{{ url_for('admin_appointments') }}"> Appointments </a> </div> """,
        counts=counts,
    )


@app.route("/admin/users")
@admin_required
def admin_users():
    rows = db_select(
        "profiles",
        order="created_at.desc",
        limit=300
    )

    return render_page(
        "Admin Users",
        r""" <div class="card"> <h2>Users</h2> <table> <thead> <tr> <th>Name</th> <th>Email</th> <th>Phone</th> <th>Role</th> <th>Admin</th> </tr> </thead> <tbody> {% for u in rows %} <tr> <td> {{ u.get("full_name") or u.get("name") }} </td> <td>{{ u.get("email") }}</td> <td>{{ u.get("phone") or "" }}</td> <td>{{ u.get("role") or "" }}</td> <td> {{ "Yes" if u.get("is_admin") else "No" }} </td> </tr> {% endfor %} </tbody> </table> </div> """,
        rows=rows,
    )


@app.route("/admin/drivers")
@admin_required
def admin_drivers():
    rows = db_select(
        "driver_profiles",
        order="created_at.desc",
        limit=300
    )

    return render_page(
        "Admin Drivers",
        r""" <div class="card"> <h2>Drivers</h2> <table> <thead> <tr> <th>Provider ID</th> <th>Vehicle</th> <th>Registration</th> <th>Licence</th> <th>Verification</th> </tr> </thead> <tbody> {% for d in rows %} <tr> <td>{{ d.get("provider_id") }}</td> <td> {{ d.get("vehicle_type") }} {{ d.get("vehicle_make") or "" }} {{ d.get("vehicle_model") or "" }} </td> <td> {{ d.get("vehicle_registration") }} </td> <td> {{ d.get("driving_license_number") }} </td> <td> {{ d.get("verification_status") }} </td> </tr> {% endfor %} </tbody> </table> </div> """,
        rows=rows,
    )


@app.route("/admin/deliveries")
@admin_required
def admin_deliveries():
    rows = db_select(
        "deliveries",
        order="created_at.desc",
        limit=300
    )

    return render_page(
        "Admin Deliveries",
        r""" <div class="card"> <h2>Deliveries</h2> <table> <thead> <tr> <th>Tracking</th> <th>Customer</th> <th>Pickup</th> <th>Destination</th> <th>Driver</th> <th>Status</th> </tr> </thead> <tbody> {% for d in rows %} <tr> <td>{{ d.get("tracking_code") }}</td> <td>{{ d.get("customer_id") }}</td> <td>{{ d.get("pickup_location") }}</td> <td>{{ d.get("destination") }}</td> <td> {{ d.get("driver_id") or "Unassigned" }} </td> <td>{{ d.get("status") }}</td> </tr> {% endfor %} </tbody> </table> </div> """,
        rows=rows,
    )


@app.route("/admin/appointments")
@admin_required
def admin_appointments():
    rows = db_select(
        "appointments",
        order="created_at.desc",
        limit=300
    )

    return render_page(
        "Admin Appointments",
        r""" <div class="card"> <h2>Appointments</h2> <table> <thead> <tr> <th>Date</th> <th>Client</th> <th>Provider</th> <th>Type</th> <th>Status</th> </tr> </thead> <tbody> {% for a in rows %} <tr> <td>{{ a.get("appointment_date") }}</td> <td>{{ a.get("client_id") }}</td> <td>{{ a.get("provider_id") }}</td> <td>{{ a.get("appointment_type") }}</td> <td>{{ a.get("status") }}</td> </tr> {% endfor %} </tbody> </table> </div> """,
        rows=rows,
    )


# ============================================================
# ERROR HANDLERS
# ============================================================

@app.errorhandler(404)
def not_found(error):
    return render_page(
        "Not Found",
        r""" <div class="card"> <h2>Page Not Found</h2> <p>The requested page does not exist.</p> <a class="btn" href="{{ url_for('home') }}"> Return Home </a> </div> """
    ), 404


@app.errorhandler(413)
def too_large(error):
    return render_page(
        "File Too Large",
        r""" <div class="card"> <h2>File Too Large</h2> <p> The maximum upload size is {{ max_mb }} MB. </p> </div> """,
        max_mb=MAX_UPLOAD_MB,
    ), 413


@app.errorhandler(500)
def internal_error(error):
    logger.exception(
        "Unhandled application error"
    )

    return render_page(
        "Server Error",
        r""" <div class="card"> <h2>KOJA AFRICA Server Error</h2> <p> The server encountered an unexpected error. Check Render logs for details. </p> <a class="btn" href="{{ url_for('home') }}"> Return Home </a> </div> """
    ), 500


@app.before_request
def before_request():
    # Deliberately empty.
    # Never connect to Supabase at application startup.
    pass


@app.context_processor
def inject_globals():
    return {
        "APP_NAME": APP_NAME,
        "APP_TAGLINE": APP_TAGLINE,
    }


# ============================================================
# RENDER START
# ============================================================

if __name__ == "__main__":
    port = int(
        os.getenv("PORT", "5000")
    )

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )

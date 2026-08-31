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
    Flask,
    request,
    redirect,
    url_for,
    session,
    render_template_string,
    flash,
    send_file,
    jsonify,
    abort,
)

from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename


# ============================================================
# KOJA AFRICA
# Knowledge • Questions • Answers
#
# Single-file Flask application
# Flask + Supabase REST + Supabase Storage
#
# IMPORTANT
# - No psycopg
# - No psycopg2
# - No database connection at startup
# - Uses Supabase REST API
# - Email/password login works with local profiles
# - Optional Supabase Auth login is supported
# - Driver GPS uses driver_locations
# - Customers can find nearby online drivers
# - Customers can send delivery requests
# ============================================================


load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("koja-africa")


# ============================================================
# APP CONFIGURATION
# ============================================================

app = Flask(__name__)

app.secret_key = os.getenv(
    "SECRET_KEY",
    os.getenv(
        "FLASK_SECRET_KEY",
        secrets.token_hex(32)
    )
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
    "pdf",
    "doc",
    "docx",
    "txt",
    "jpg",
    "jpeg",
    "png",
    "webp",
}


# ============================================================
# GENERAL HELPERS
# ============================================================

def utc_now():
    return datetime.now(timezone.utc).isoformat()


def supabase_configured():
    return bool(
        SUPABASE_URL and
        SUPABASE_SERVICE_KEY
    )


def clean(value):
    if value is None:
        return ""
    return str(value).strip()


def first_nonempty(*values):
    for value in values:
        if value is not None and str(value).strip():
            return value
    return ""


def safe_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def json_or_empty(response):
    try:
        return response.json()
    except Exception:
        return {}


# ============================================================
# SUPABASE REST HELPERS
# ============================================================

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
    return (
        f"{SUPABASE_URL}/rest/v1/"
        f"{quote(str(table), safe='')}"
    )


def sb_storage_url(path):
    return (
        f"{SUPABASE_URL}/storage/v1/object/"
        f"{quote(STORAGE_BUCKET, safe='')}/"
        f"{quote(path, safe='/')}"
    )


def db_select(
    table,
    filters=None,
    select="*",
    order=None,
    limit=None,
):
    if not supabase_configured():
        logger.error("Supabase is not configured.")
        return []

    params = {
        "select": select
    }

    if filters:
        for key, value in filters.items():

            if value is None:
                params[key] = "is.null"

            elif (
                isinstance(value, str)
                and value.startswith(
                    (
                        "eq.",
                        "neq.",
                        "gt.",
                        "gte.",
                        "lt.",
                        "lte.",
                        "in.",
                        "is.",
                        "like.",
                        "ilike.",
                    )
                )
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

        if isinstance(data, list):
            return data

        return []

    except Exception as exc:
        logger.exception(
            "SELECT %s error: %s",
            table,
            exc,
        )
        return []


def db_insert(
    table,
    payload,
    returning="representation",
):
    if not supabase_configured():
        return None, "Supabase is not configured."

    try:
        response = requests.post(
            sb_rest_url(table),
            headers=sb_headers(
                {
                    "Prefer": f"return={returning}"
                }
            ),
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
            return (
                data[0] if data else None,
                None,
            )

        return data, None

    except Exception as exc:
        logger.exception(
            "INSERT %s error: %s",
            table,
            exc,
        )

        return None, str(exc)


def db_update(
    table,
    filters,
    payload,
):
    if not supabase_configured():
        return None, "Supabase is not configured."

    params = {}

    for key, value in filters.items():
        if value is None:
            params[key] = "is.null"
        else:
            params[key] = f"eq.{value}"

    try:
        response = requests.patch(
            sb_rest_url(table),
            headers=sb_headers(
                {
                    "Prefer": "return=representation"
                }
            ),
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
        logger.exception(
            "UPDATE %s error: %s",
            table,
            exc,
        )

        return None, str(exc)


def db_delete(table, filters):
    if not supabase_configured():
        return False, "Supabase is not configured."

    params = {}

    for key, value in filters.items():
        if value is None:
            params[key] = "is.null"
        else:
            params[key] = f"eq.{value}"

    try:
        response = requests.delete(
            sb_rest_url(table),
            headers=sb_headers(),
            params=params,
            timeout=20,
        )

        if not response.ok:
            return False, response.text

        return True, None

    except Exception as exc:
        logger.exception(
            "DELETE %s error: %s",
            table,
            exc,
        )

        return False, str(exc)


def table_exists(table):
    if not supabase_configured():
        return False

    try:
        response = requests.get(
            sb_rest_url(table),
            headers=sb_headers(),
            params={
                "select": "*",
                "limit": "1",
            },
            timeout=10,
        )

        return response.status_code < 400

    except Exception:
        return False


def first_row(table, filters):
    rows = db_select(
        table,
        filters=filters,
        limit=1,
    )

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
            "KOJA User",
        ),

        "email": user.get("email"),

        "phone": user.get("phone"),

        "role": (
            user.get("role")
            or "student"
        ),

        "is_admin": bool(
            user.get("is_admin", False)
        ),

        "institution": user.get(
            "institution"
        ),

        "student_number": user.get(
            "student_number"
        ),

        "vehicle_type": user.get(
            "vehicle_type"
        ),

        "vehicle_number": user.get(
            "vehicle_number"
        ),
    }

    if auth_session:
        session["supabase_access_token"] = (
            auth_session.get("access_token")
        )

        session["supabase_refresh_token"] = (
            auth_session.get("refresh_token")
        )

    session.permanent = True


def find_user_by_email(email):
    email = clean(email).lower()

    if not email:
        return None

    # profiles is the primary authentication table.
    for table in (
        "profiles",
        "koja_users",
        "users",
        "KOJA ZM",
    ):
        try:
            rows = db_select(
                table,
                filters={
                    "email": email
                },
                limit=1,
            )

            if rows:
                return rows[0]

        except Exception:
            continue

    return None


def find_user_by_id(user_id):
    if not user_id:
        return None

    for table in (
        "profiles",
        "koja_users",
        "users",
        "KOJA ZM",
    ):
        try:
            rows = db_select(
                table,
                filters={
                    "id": user_id
                },
                limit=1,
            )

            if rows:
                return rows[0]

        except Exception:
            continue

    return None


def password_matches(user, password):
    if not user or not password:
        return False

    stored = first_nonempty(
        user.get("password_hash"),
        user.get("encrypted_password"),
    )

    if not stored:
        return False

    try:
        return check_password_hash(
            stored,
            password,
        )

    except Exception:
        return False


def supabase_auth_login(email, password):
    """
    Optional Supabase Auth compatibility.

    This is only used when a user does not have a
    matching local password_hash.
    """

    if not SUPABASE_URL:
        return None

    key = (
        SUPABASE_ANON_KEY
        or SUPABASE_SERVICE_KEY
    )

    if not key:
        return None

    try:
        response = requests.post(
            f"{SUPABASE_URL}/auth/v1/token",
            params={
                "grant_type": "password"
            },
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
                "Supabase Auth login failed: %s %s",
                response.status_code,
                response.text[:500],
            )

            return None

        return json_or_empty(response)

    except Exception as exc:
        logger.exception(
            "Supabase Auth login error: %s",
            exc,
        )

        return None


# ============================================================
# STORAGE
# ============================================================

def upload_storage(
    file_storage,
    folder="uploads",
):
    if not file_storage:
        return None, "No file supplied."

    if not file_storage.filename:
        return None, "No file supplied."

    if not supabase_configured():
        return None, "Supabase is not configured."

    filename = secure_filename(
        file_storage.filename
    )

    if not filename:
        return None, "Invalid filename."

    if "." in filename:
        extension = (
            filename.rsplit(".", 1)[-1]
            .lower()
        )
    else:
        extension = ""

    if extension not in ALLOWED_EXTENSIONS:
        return (
            None,
            f"File type .{extension} is not allowed.",
        )

    data = file_storage.read()

    if len(data) > MAX_UPLOAD_MB * 1024 * 1024:
        return (
            None,
            f"Maximum file size is {MAX_UPLOAD_MB} MB.",
        )

    path = (
        f"{folder.strip('/')}/"
        f"{uuid.uuid4().hex}_"
        f"{filename}"
    )

    mime = (
        file_storage.mimetype
        or "application/octet-stream"
    )

    try:
        response = requests.post(
            sb_storage_url(path),
            headers=sb_headers(
                {
                    "Content-Type": mime,
                    "x-upsert": "true",
                }
            ),
            data=data,
            timeout=60,
        )

        if not response.ok:
            logger.error(
                "Storage upload failed: %s %s",
                response.status_code,
                response.text[:1200],
            )

            return None, response.text[:1200]

        public_url = (
            f"{SUPABASE_URL}"
            f"/storage/v1/object/public/"
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
        logger.exception(
            "Storage upload error: %s",
            exc,
        )

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
# AUTH DECORATORS
# ============================================================

def login_required(function):
    @wraps(function)
    def wrapper(*args, **kwargs):

        if not current_user():
            flash(
                "Please log in first.",
                "warning",
            )

            return redirect(
                url_for(
                    "login",
                    next=request.path,
                )
            )

        return function(*args, **kwargs)

    return wrapper


def admin_required(function):
    @wraps(function)
    def wrapper(*args, **kwargs):

        user = current_user()

        if not user:
            flash(
                "Administrator login required.",
                "warning",
            )

            return redirect(
                url_for("login")
            )

        if not user.get("is_admin"):
            flash(
                "Administrator access required.",
                "danger",
            )

            return redirect(
                url_for("dashboard")
            )

        return function(*args, **kwargs)

    return wrapper


def driver_required(function):
    @wraps(function)
    def wrapper(*args, **kwargs):

        user = current_user()

        if not user:
            flash(
                "Driver login required.",
                "warning",
            )

            return redirect(
                url_for("login")
            )

        if (
            user.get("role") not in (
                "driver",
                "admin",
            )
            and not user.get("is_admin")
        ):
            flash(
                "Driver account required.",
                "danger",
            )

            return redirect(
                url_for("dashboard")
            )

        return function(*args, **kwargs)

    return wrapper


# ============================================================
# ACTIVITY LOGGING
# ============================================================

def log_activity(
    action,
    description="",
    user_id=None,
):
    uid = (
        user_id
        or (current_user() or {}).get("id")
    )

    payload = {
        "action": action,
        "description": description,
    }

    if uid:
        payload["user_id"] = uid

    try:
        db_insert(
            "activity_logs",
            payload,
        )
    except Exception:
        pass


# ============================================================
# GEOLOCATION
# ============================================================

def haversine_km(
    lat1,
    lon1,
    lat2,
    lon2,
):
    radius = 6371.0088

    p1 = math.radians(lat1)
    p2 = math.radians(lat2)

    dp = math.radians(
        lat2 - lat1
    )

    dl = math.radians(
        lon2 - lon1
    )

    a = (
        math.sin(dp / 2) ** 2
        +
        math.cos(p1)
        * math.cos(p2)
        * math.sin(dl / 2) ** 2
    )

    return (
        radius
        * 2
        * math.atan2(
            math.sqrt(a),
            math.sqrt(1 - a),
        )
    )


def latest_driver_locations():
    rows = db_select(
        "driver_locations",
        order="created_at.desc",
        limit=2000,
    )

    latest = {}

    for row in rows:

        driver_id = (
            row.get("driver_id")
            or row.get("user_id")
        )

        if not driver_id:
            continue

        key = str(driver_id)

        if key not in latest:
            latest[key] = row

    return latest


# ============================================================
# SERVICE PROVIDERS
# ============================================================

def get_driver_provider(user_id):
    if not user_id:
        return None

    return first_row(
        "service_providers",
        {
            "user_id": user_id,
            "provider_type": "driver",
        },
    )


def ensure_driver_provider(user):
    provider = get_driver_provider(
        user.get("id")
    )

    if provider:
        return provider, None

    payload = {
        "id": str(uuid.uuid4()),
        "user_id": user.get("id"),
        "provider_type": "driver",
        "full_name": (
            user.get("name")
            or user.get("full_name")
            or "Driver"
        ),
        "phone": user.get("phone") or None,
        "email": user.get("email") or None,
        "verification_status": "pending",
        "is_available": False,
        "is_active": True,
    }

    provider, error = db_insert(
        "service_providers",
        payload,
    )

    if error:
        return None, error

    return provider or payload, None


# ============================================================
# HTML BASE
# ============================================================

BASE_HTML = r"""
<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">

    <meta
        name="viewport"
        content="width=device-width,
        initial-scale=1"
    >

    <title>
        {{ title or "KOJA AFRICA" }}
    </title>

    <style>
        * {
            box-sizing: border-box;
        }

        body {
            margin: 0;
            font-family:
                Arial,
                Helvetica,
                sans-serif;
            background: #f5f7fb;
            color: #172033;
        }

        nav {
            background: #111827;
            color: white;
            padding: 14px;
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            align-items: center;
        }

        nav a {
            color: white;
            text-decoration: none;
            padding: 8px 10px;
            border-radius: 7px;
        }

        nav a:hover {
            background: #263244;
        }

        .brand {
            font-weight: bold;
            font-size: 20px;
            margin-right: 10px;
        }

        main {
            max-width: 1100px;
            margin: auto;
            padding: 20px;
        }

        .card {
            background: white;
            padding: 20px;
            margin: 14px 0;
            border-radius: 12px;
            box-shadow:
                0 2px 10px
                rgba(0,0,0,.06);
        }

        .grid {
            display: grid;
            grid-template-columns:
                repeat(auto-fit,
                minmax(220px,1fr));
            gap: 15px;
        }

        input,
        select,
        textarea {
            width: 100%;
            padding: 11px;
            margin-top: 6px;
            margin-bottom: 13px;
            border: 1px solid #ccd2dc;
            border-radius: 7px;
            font-size: 15px;
        }

        textarea {
            min-height: 120px;
        }

        button,
        .btn {
            display: inline-block;
            background: #2563eb;
            color: white;
            border: 0;
            padding: 11px 16px;
            border-radius: 7px;
            text-decoration: none;
            cursor: pointer;
            margin: 3px;
        }

        .btn-green {
            background: #16a34a;
        }

        .btn-red {
            background: #dc2626;
        }

        .btn-dark {
            background: #111827;
        }

        .alert {
            padding: 12px;
            border-radius: 7px;
            margin-bottom: 10px;
            background: #e5e7eb;
        }

        .success {
            background: #dcfce7;
            color: #166534;
        }

        .danger {
            background: #fee2e2;
            color: #991b1b;
        }

        .warning {
            background: #fef3c7;
            color: #92400e;
        }

        .muted {
            color: #64748b;
        }

        .stat {
            text-align: center;
        }

        .stat strong {
            font-size: 30px;
            display: block;
        }

        footer {
            padding: 30px;
            text-align: center;
            color: #64748b;
        }
    </style>
</head>

<body>

<nav>

    <span class="brand">
        KOJA AFRICA
    </span>

    <a href="{{ url_for('home') }}">
        Home
    </a>

    {% if user %}

        <a href="{{ url_for('dashboard') }}">
            Dashboard
        </a>

        <a href="{{ url_for('services') }}">
            Services
        </a>

        <a href="{{ url_for('questions') }}">
            Questions
        </a>

        <a href="{{ url_for('assignments') }}">
            Assignments
        </a>

        <a href="{{ url_for('universities') }}">
            Universities
        </a>

        <a href="{{ url_for('deliveries') }}">
            Deliveries
        </a>

        <a href="{{ url_for('drivers') }}">
            Drivers
        </a>

        <a href="{{ url_for('cv') }}">
            CV
        </a>

        {% if user.role in
            ['driver','admin']
            or user.is_admin %}

            <a href="{{ url_for('driver_dashboard') }}">
                Driver
            </a>

        {% endif %}

        {% if user.is_admin %}
            <a href="{{ url_for('admin') }}">
                Admin
            </a>
        {% endif %}

        <a href="{{ url_for('logout') }}">
            Logout
        </a>

    {% else %}

        <a href="{{ url_for('login') }}">
            Login
        </a>

        <a href="{{ url_for('register') }}">
            Register
        </a>

    {% endif %}

</nav>

<main>

    {% with messages =
        get_flashed_messages(
            with_categories=true
        )
    %}

        {% for category, message in messages %}

            <div class="alert {{ category }}">
                {{ message }}
            </div>

        {% endfor %}

    {% endwith %}

    {{ body|safe }}

</main>

<footer>
    KOJA AFRICA —
    Knowledge • Questions • Answers
</footer>

</body>
</html>
"""


def render_page(
    title,
    body_template,
    **context,
):
    context["user"] = current_user()

    body = render_template_string(
        body_template,
        **context,
    )

    return render_template_string(
        BASE_HTML,
        title=title,
        body=body,
        user=current_user(),
    )


# ============================================================
# HOME
# ============================================================

@app.route("/")
def home():

    return render_page(
        "KOJA AFRICA",
        r"""
        <div class="card">

            <h1>
                KOJA AFRICA
            </h1>

            <p>
                Knowledge • Questions • Answers
            </p>

            <p>
                Academic services, university
                applications, CV creation,
                farmer registration,
                professional bookings and
                delivery services.
            </p>

            {% if not user %}

                <a class="btn"
                   href="{{ url_for('register') }}">
                    Create Account
                </a>

                <a class="btn btn-dark"
                   href="{{ url_for('login') }}">
                    Login
                </a>

            {% endif %}

        </div>

        <div class="grid">

            <div class="card">
                <h3>Academic</h3>
                <p>
                    Questions and assignments.
                </p>
                <a class="btn"
                   href="{{ url_for('questions') }}">
                    Questions
                </a>
            </div>

            <div class="card">
                <h3>Universities</h3>
                <p>
                    University applications.
                </p>
                <a class="btn"
                   href="{{ url_for('universities') }}">
                    Universities
                </a>
            </div>

            <div class="card">
                <h3>CV</h3>
                <p>
                    Create a professional CV.
                </p>
                <a class="btn"
                   href="{{ url_for('cv') }}">
                    Create CV
                </a>
            </div>

            <div class="card">
                <h3>Farmers</h3>
                <p>
                    Agricultural registration.
                </p>
                <a class="btn"
                   href="{{ url_for('farmer') }}">
                    Farmer Portal
                </a>
            </div>

            <div class="card">
                <h3>Doctors</h3>
                <p>
                    Find and book doctors.
                </p>
                <a class="btn"
                   href="{{ url_for('doctors') }}">
                    Doctors
                </a>
            </div>

            <div class="card">
                <h3>Teachers</h3>
                <p>
                    Find tutors and teachers.
                </p>
                <a class="btn"
                   href="{{ url_for('teachers') }}">
                    Teachers
                </a>
            </div>

            <div class="card">
                <h3>Deliveries</h3>
                <p>
                    Find nearby drivers.
                </p>
                <a class="btn"
                   href="{{ url_for('drivers') }}">
                    Delivery Drivers
                </a>
            </div>

            <div class="card">
                <h3>Live GPS</h3>
                <p>
                    Drivers can share GPS.
                </p>
                <a class="btn"
                   href="{{ url_for('tracking') }}">
                    Driver GPS
                </a>
            </div>

        </div>
        """,
    )


@app.route("/health")
def health():

    return jsonify({
        "status": "ok",
        "application": APP_NAME,
        "supabase_configured":
            supabase_configured(),
        "gps_table_available":
            table_exists("driver_locations"),
        "timestamp": utc_now(),
        "python":
            os.sys.version.split()[0],
    })


# ============================================================
# REGISTER
# ============================================================

@app.route(
    "/register",
    methods=["GET", "POST"],
)
def register():

    if request.method == "POST":

        full_name = clean(
            request.form.get("full_name")
        )

        email = clean(
            request.form.get("email")
        ).lower()

        phone = clean(
            request.form.get("phone")
        )

        password = request.form.get(
            "password",
            "",
        )

        role = clean(
            request.form.get("role")
        ) or "student"

        if role not in (
            "student",
            "driver",
            "teacher",
            "doctor",
        ):
            role = "student"

        if not full_name:
            flash(
                "Full name is required.",
                "danger",
            )
            return redirect(
                url_for("register")
            )

        if not email:
            flash(
                "Email is required.",
                "danger",
            )
            return redirect(
                url_for("register")
            )

        if not password:
            flash(
                "Password is required.",
                "danger",
            )
            return redirect(
                url_for("register")
            )

        if len(password) < 6:
            flash(
                "Password must contain at least 6 characters.",
                "danger",
            )
            return redirect(
                url_for("register")
            )

        existing = find_user_by_email(
            email
        )

        if existing:
            flash(
                "An account with this email already exists. Please log in.",
                "warning",
            )

            return redirect(
                url_for("login")
            )

        user_id = str(uuid.uuid4())

        password_hash = generate_password_hash(
            password
        )

        payload = {
            "id": user_id,
            "full_name": full_name,
            "name": full_name,
            "email": email,
            "phone": phone or None,
            "password_hash": password_hash,
            "role": role,
            "is_admin": False,
            "is_active": True,
            "created_at": utc_now(),
        }

        row, error = db_insert(
            "profiles",
            payload,
        )

        if error:

            logger.error(
                "profiles registration failed: %s",
                error,
            )

            # Compatibility fallback for
            # installations where profiles has
            # a different schema.
            fallback = {
                "id": user_id,
                "full_name": full_name,
                "email": email,
                "phone": phone or None,
                "password_hash": password_hash,
            }

            row, error = db_insert(
                "KOJA ZM",
                fallback,
            )

        if error:

            logger.error(
                "Registration failed: %s",
                error,
            )

            flash(
                "Registration failed. "
                "Check Render logs for the exact Supabase column error.",
                "danger",
            )

            return redirect(
                url_for("register")
            )

        login_user(
            row or payload
        )

        log_activity(
            "registration",
            "New KOJA account registered.",
        )

        flash(
            "Account created successfully.",
            "success",
        )

        return redirect(
            url_for("dashboard")
        )

    return render_page(
        "Register",
        r"""
        <div class="card">

            <h2>
                Create KOJA Account
            </h2>

            <form method="POST">

                <label>
                    Full Name
                </label>

                <input
                    name="full_name"
                    required
                >

                <label>
                    Email
                </label>

                <input
                    type="email"
                    name="email"
                    required
                >

                <label>
                    Phone
                </label>

                <input
                    name="phone"
                >

                <label>
                    Account Type
                </label>

                <select name="role">

                    <option value="student">
                        Student / Customer
                    </option>

                    <option value="driver">
                        Delivery Driver
                    </option>

                    <option value="teacher">
                        Teacher / Tutor
                    </option>

                    <option value="doctor">
                        Doctor
                    </option>

                </select>

                <label>
                    Password
                </label>

                <input
                    type="password"
                    name="password"
                    minlength="6"
                    required
                >

                <button type="submit">
                    Create Account
                </button>

            </form>

            <p>
                Already registered?
                <a href="{{ url_for('login') }}">
                    Login
                </a>
            </p>

        </div>
        """,
    )


# ============================================================
# LOGIN
# ============================================================

@app.route(
    "/login",
    methods=["GET", "POST"],
)
def login():

    if request.method == "POST":

        email = clean(
            request.form.get("email")
        ).lower()

        password = request.form.get(
            "password",
            "",
        )

        if not email or not password:
            flash(
                "Email and password are required.",
                "danger",
            )

            return redirect(
                url_for("login")
            )

        user = find_user_by_email(
            email
        )

        # ----------------------------------------------------
        # LOCAL EMAIL/PASSWORD LOGIN
        # ----------------------------------------------------

        if user and password_matches(
            user,
            password,
        ):

            if user.get("is_active") is False:
                flash(
                    "This account is inactive.",
                    "danger",
                )

                return redirect(
                    url_for("login")
                )

            login_user(user)

            log_activity(
                "login",
                "User logged into KOJA.",
            )

            next_url = request.args.get(
                "next",
                "",
            )

            if next_url.startswith("/"):
                return redirect(next_url)

            return redirect(
                url_for("dashboard")
            )

        # ----------------------------------------------------
        # OPTIONAL SUPABASE AUTH LOGIN
        # ----------------------------------------------------

        auth = supabase_auth_login(
            email,
            password,
        )

        if auth and auth.get("user"):

            auth_user = auth["user"]

            profile = find_user_by_id(
                auth_user.get("id")
            )

            if not profile:

                metadata = (
                    auth_user.get(
                        "user_metadata"
                    )
                    or {}
                )

                profile, profile_error = (
                    db_insert(
                        "profiles",
                        {
                            "id":
                                auth_user.get("id"),
                            "email":
                                auth_user.get(
                                    "email"
                                ) or email,
                            "full_name":
                                metadata.get(
                                    "full_name"
                                ) or email,
                            "name":
                                metadata.get(
                                    "full_name"
                                ) or email,
                            "role":
                                "student",
                            "is_admin":
                                False,
                            "is_active":
                                True,
                        },
                    )
                )

                if profile_error:
                    logger.error(
                        "Could not create Auth profile: %s",
                        profile_error,
                    )

            if profile:

                login_user(
                    profile,
                    auth,
                )

                log_activity(
                    "login",
                    "User logged in through Supabase Auth.",
                )

                return redirect(
                    url_for("dashboard")
                )

        flash(
            "Invalid login credentials. "
            "Use the same email and password used to create the KOJA account.",
            "danger",
        )

        return redirect(
            url_for("login")
        )

    return render_page(
        "Login",
        r"""
        <div class="card">

            <h2>
                KOJA Login
            </h2>

            <form method="POST">

                <label>
                    Email
                </label>

                <input
                    type="email"
                    name="email"
                    required
                >

                <label>
                    Password
                </label>

                <input
                    type="password"
                    name="password"
                    required
                >

                <button type="submit">
                    Login
                </button>

            </form>

            <p>
                No account?
                <a href="{{ url_for('register') }}">
                    Create one
                </a>
            </p>

        </div>
        """,
    )


# ============================================================
# LOGOUT
# ============================================================

@app.route("/logout")
def logout():

    if current_user():
        log_activity(
            "logout",
            "User logged out.",
        )

    session.clear()

    flash(
        "You have been logged out.",
        "success",
    )

    return redirect(
        url_for("home")
    )


# ============================================================
# DASHBOARD
# ============================================================

@app.route("/dashboard")
@login_required
def dashboard():

    user = current_user()

    questions_count = len(
        db_select(
            "questions",
            filters={
                "student_id":
                    user["id"]
            },
            limit=1000,
        )
    )

    deliveries_count = len(
        db_select(
            "deliveries",
            filters={
                "customer_id":
                    user["id"]
            },
            limit=1000,
        )
    )

    appointments_count = len(
        db_select(
            "appointments",
            filters={
                "client_id":
                    user["id"]
            },
            limit=1000,
        )
    )

    return render_page(
        "Dashboard",
        r"""
        <div class="card">

            <h2>
                Welcome,
                {{ user.name }}
            </h2>

            <p>
                {{ user.email }}
            </p>

        </div>

        <div class="grid">

            <div class="card stat">
                <strong>
                    {{ questions_count }}
                </strong>
                Academic Questions
            </div>

            <div class="card stat">
                <strong>
                    {{ deliveries_count }}
                </strong>
                Deliveries
            </div>

            <div class="card stat">
                <strong>
                    {{ appointments_count }}
                </strong>
                Appointments
            </div>

            <div class="card stat">
                <strong>
                    {{ "ADMIN"
                       if user.is_admin
                       else user.role|upper }}
                </strong>
                Account
            </div>

        </div>

        <div class="card">

            <h2>
                KOJA Services
            </h2>

            <a class="btn"
               href="{{ url_for('cv') }}">
                Create CV
            </a>

            <a class="btn"
               href="{{ url_for('universities') }}">
                University Application
            </a>

            <a class="btn"
               href="{{ url_for('farmer') }}">
                Farmer Registration
            </a>

            <a class="btn"
               href="{{ url_for('doctors') }}">
                Doctor Booking
            </a>

            <a class="btn"
               href="{{ url_for('teachers') }}">
                Teacher Booking
            </a>

            <a class="btn"
               href="{{ url_for('drivers') }}">
                Find Driver
            </a>

            {% if user.role in
                ['driver','admin']
                or user.is_admin %}

                <a class="btn btn-green"
                   href="{{ url_for('driver_dashboard') }}">
                    Driver Dashboard
                </a>

            {% endif %}

        </div>
        """,
        questions_count=questions_count,
        deliveries_count=deliveries_count,
        appointments_count=appointments_count,
    )


# ============================================================
# SERVICES
# ============================================================

@app.route("/services")
@login_required
def services():

    return render_page(
        "Services",
        r"""
        <div class="card">

            <h2>
                KOJA Services
            </h2>

            <div class="grid">

                <a class="btn"
                   href="{{ url_for('questions') }}">
                    Academic Questions
                </a>

                <a class="btn"
                   href="{{ url_for('assignments') }}">
                    Assignments
                </a>

                <a class="btn"
                   href="{{ url_for('cv') }}">
                    CV
                </a>

                <a class="btn"
                   href="{{ url_for('universities') }}">
                    Universities
                </a>

                <a class="btn"
                   href="{{ url_for('farmer') }}">
                    Farmer Registration
                </a>

                <a class="btn"
                   href="{{ url_for('doctors') }}">
                    Doctors
                </a>

                <a class="btn"
                   href="{{ url_for('teachers') }}">
                    Teachers
                </a>

                <a class="btn"
                   href="{{ url_for('deliveries') }}">
                    Deliveries
                </a>

            </div>

        </div>
        """,
    )


# ============================================================
# QUESTIONS
# ============================================================

@app.route(
    "/questions",
    methods=["GET", "POST"],
)
@login_required
def questions():

    user = current_user()

    if request.method == "POST":

        question_text = clean(
            request.form.get(
                "question"
            )
        )

        subject = clean(
            request.form.get(
                "subject"
            )
        )

        if not question_text:

            flash(
                "Enter your question.",
                "danger",
            )

            return redirect(
                url_for("questions")
            )

        payload = {
            "id": str(uuid.uuid4()),
            "student_id":
                str(user["id"]),
            "student_name":
                user.get("name")
                or "KOJA Student",
            "question":
                question_text,
            "answer": "",
            "answer_by": "",
            "subject":
                subject or None,
            "status": "pending",
            "created_at":
                utc_now(),
        }

        row, error = db_insert(
            "questions",
            payload,
        )

        if error:

            logger.error(
                "Question insert failed: %s",
                error,
            )

            flash(
                "Question could not be submitted. "
                "Check your questions table columns.",
                "danger",
            )

        else:

            flash(
                "Question submitted.",
                "success",
            )

            log_activity(
                "question_created",
                "Student submitted an academic question.",
            )

        return redirect(
            url_for("questions")
        )

    rows = db_select(
        "questions",
        filters={
            "student_id":
                user["id"]
        },
        order="created_at.desc",
        limit=100,
    )

    return render_page(
        "Questions",
        r"""
        <div class="card">

            <h2>
                Ask an Academic Question
            </h2>

            <form method="POST">

                <label>
                    Subject
                </label>

                <input
                    name="subject"
                    placeholder="e.g. Biology"
                >

                <label>
                    Question
                </label>

                <textarea
                    name="question"
                    required
                ></textarea>

                <button type="submit">
                    Submit Question
                </button>

            </form>

        </div>

        <div class="card">

            <h2>
                My Questions
            </h2>

            {% for q in rows %}

                <div class="card">

                    <strong>
                        {{ q.get("subject")
                           or "Academic" }}
                    </strong>

                    <p>
                        {{ q.get("question")
                           or
                           q.get("question_text")
                           or "" }}
                    </p>

                    {% if q.get("answer") %}

                        <h4>
                            Answer
                        </h4>

                        <p>
                            {{ q.get("answer") }}
                        </p>

                    {% endif %}

                    <p class="muted">
                        Status:
                        {{ q.get("status")
                           or "Submitted" }}
                    </p>

                </div>

            {% else %}

                <p>
                    No questions submitted yet.
                </p>

            {% endfor %}

        </div>
        """,
        rows=rows,
    )


# ============================================================
# ASSIGNMENTS
# ============================================================

@app.route(
    "/assignments",
    methods=["GET", "POST"],
)
@login_required
def assignments():

    user = current_user()

    if request.method == "POST":

        title = clean(
            request.form.get("title")
        )

        description = clean(
            request.form.get(
                "description"
            )
        )

        file_storage = request.files.get(
            "file"
        )

        uploaded = None

        if file_storage and file_storage.filename:

            uploaded, error = upload_storage(
                file_storage,
                "assignments",
            )

            if error:

                flash(
                    f"Upload failed: {error}",
                    "danger",
                )

                return redirect(
                    url_for("assignments")
                )

        payload = {
            "id": str(uuid.uuid4()),
            "student_id":
                user["id"],
            "user_id":
                user["id"],
            "title":
                title,
            "description":
                description,
            "status":
                "submitted",
            "created_at":
                utc_now(),
        }

        if uploaded:

            payload.update({
                "file_name":
                    uploaded["file_name"],
                "file_path":
                    uploaded["path"],
                "file_url":
                    uploaded["url"],
                "file_size":
                    uploaded["file_size"],
                "mime_type":
                    uploaded["mime_type"],
            })

        row, error = db_insert(
            "assignments",
            payload,
        )

        if error:

            logger.error(
                "Assignment insert failed: %s",
                error,
            )

            minimal = {
                "id":
                    payload["id"],
                "title":
                    title,
                "description":
                    description,
            }

            if uploaded:
                minimal.update({
                    "file_name":
                        uploaded["file_name"],
                    "file_path":
                        uploaded["path"],
                    "file_url":
                        uploaded["url"],
                })

            row, error = db_insert(
                "assignments",
                minimal,
            )

        if error:

            flash(
                "Assignment could not be saved. "
                "Check assignments table columns.",
                "danger",
            )

        else:

            flash(
                "Assignment uploaded successfully.",
                "success",
            )

        return redirect(
            url_for("assignments")
        )

    rows = db_select(
        "assignments",
        order="created_at.desc",
        limit=100,
    )

    return render_page(
        "Assignments",
        r"""
        <div class="card">

            <h2>
                Upload Assignment
            </h2>

            <form
                method="POST"
                enctype="multipart/form-data"
            >

                <label>
                    Assignment Title
                </label>

                <input
                    name="title"
                    required
                >

                <label>
                    Description / Question
                </label>

                <textarea
                    name="description"
                ></textarea>

                <label>
                    Assignment File
                </label>

                <input
                    type="file"
                    name="file"
                >

                <button type="submit">
                    Upload Assignment
                </button>

            </form>

        </div>

        <div class="card">

            <h2>
                Assignments
            </h2>

            {% for item in rows %}

                <div class="card">

                    <h3>
                        {{ item.get("title")
                           or "Assignment" }}
                    </h3>

                    <p>
                        {{ item.get("description")
                           or "" }}
                    </p>

                    {% if item.get("file_url") %}

                        <a
                            class="btn"
                            href="{{ item.get('file_url') }}"
                            target="_blank"
                        >
                            Download File
                        </a>

                    {% endif %}

                    {% if item.get("answer_file_url") %}

                        <a
                            class="btn btn-green"
                            href="{{ item.get('answer_file_url') }}"
                            target="_blank"
                        >
                            Download Answer
                        </a>

                    {% endif %}

                    {% if item.get("answered_file_url") %}

                        <a
                            class="btn btn-green"
                            href="{{ item.get('answered_file_url') }}"
                            target="_blank"
                        >
                            Download Answered File
                        </a>

                    {% endif %}

                </div>

            {% else %}

                <p>
                    No assignments found.
                </p>

            {% endfor %}

        </div>
        """,
        rows=rows,
    )


# ============================================================
# CV
# ============================================================

@app.route(
    "/cv",
    methods=["GET", "POST"],
)
@login_required
def cv():

    user = current_user()

    if request.method == "POST":

        data = {
            "full_name":
                clean(
                    request.form.get(
                        "full_name"
                    )
                ),

            "phone":
                clean(
                    request.form.get(
                        "phone"
                    )
                ),

            "email":
                clean(
                    request.form.get(
                        "email"
                    )
                ),

            "address":
                clean(
                    request.form.get(
                        "address"
                    )
                ),

            "profile":
                clean(
                    request.form.get(
                        "profile"
                    )
                ),

            "education":
                clean(
                    request.form.get(
                        "education"
                    )
                ),

            "experience":
                clean(
                    request.form.get(
                        "experience"
                    )
                ),

            "skills":
                clean(
                    request.form.get(
                        "skills"
                    )
                ),

            "references":
                clean(
                    request.form.get(
                        "references"
                    )
                ),
        }

        return render_page(
            "CV Preview",
            r"""
            <div class="card">

                <h1>
                    {{ data.full_name }}
                </h1>

                <p>
                    {{ data.phone }}
                    |
                    {{ data.email }}
                    |
                    {{ data.address }}
                </p>

                {% if data.profile %}
                    <h2>
                        Professional Profile
                    </h2>

                    <p>
                        {{ data.profile }}
                    </p>
                {% endif %}

                {% if data.education %}
                    <h2>
                        Education
                    </h2>

                    <p>
                        {{ data.education }}
                    </p>
                {% endif %}

                {% if data.experience %}
                    <h2>
                        Work Experience
                    </h2>

                    <p>
                        {{ data.experience }}
                    </p>
                {% endif %}

                {% if data.skills %}
                    <h2>
                        Skills
                    </h2>

                    <p>
                        {{ data.skills }}
                    </p>
                {% endif %}

                {% if data.references %}
                    <h2>
                        References
                    </h2>

                    <p>
                        {{ data.references }}
                    </p>
                {% endif %}

                <button
                    onclick="window.print()"
                >
                    Print / Save as PDF
                </button>

            </div>
            """,
            data=data,
        )

    return render_page(
        "CV Builder",
        r"""
        <div class="card">

            <h2>
                CV Builder
            </h2>

            <form method="POST">

                <label>
                    Full Name
                </label>

                <input
                    name="full_name"
                    value="{{ user.name }}"
                    required
                >

                <label>
                    Phone
                </label>

                <input
                    name="phone"
                    value="{{ user.phone or '' }}"
                >

                <label>
                    Email
                </label>

                <input
                    name="email"
                    type="email"
                    value="{{ user.email or '' }}"
                >

                <label>
                    Address
                </label>

                <input name="address">

                <label>
                    Professional Profile
                </label>

                <textarea
                    name="profile"
                ></textarea>

                <label>
                    Education
                </label>

                <textarea
                    name="education"
                ></textarea>

                <label>
                    Work Experience
                </label>

                <textarea
                    name="experience"
                ></textarea>

                <label>
                    Skills
                </label>

                <textarea
                    name="skills"
                ></textarea>

                <label>
                    References
                </label>

                <textarea
                    name="references"
                ></textarea>

                <button type="submit">
                    Generate CV
                </button>

            </form>

            <p class="muted">
                Use Print / Save as PDF
                in your Android browser.
            </p>

        </div>
        """,
    )


# ============================================================
# FARMER REGISTRATION
# ============================================================

@app.route(
    "/farmer",
    methods=["GET", "POST"],
)
@login_required
def farmer():

    user = current_user()

    if request.method == "POST":

        data = {
            "id":
                str(uuid.uuid4()),

            "user_id":
                user["id"],

            "nrc":
                clean(
                    request.form.get(
                        "nrc"
                    )
                ),

            "date_of_birth":
                request.form.get(
                    "date_of_birth"
                ) or None,

            "first_name":
                clean(
                    request.form.get(
                        "first_name"
                    )
                ),

            "middle_names":
                clean(
                    request.form.get(
                        "middle_names"
                    )
                ),

            "last_name":
                clean(
                    request.form.get(
                        "last_name"
                    )
                ),

            "gender":
                clean(
                    request.form.get(
                        "gender"
                    )
                ),

            "phone":
                clean(
                    request.form.get(
                        "phone"
                    )
                ),

            "location":
                clean(
                    request.form.get(
                        "location"
                    )
                ),

            "payment_method":
                clean(
                    request.form.get(
                        "payment_method"
                    )
                ),

            "provider":
                clean(
                    request.form.get(
                        "provider"
                    )
                ),

            "branch":
                clean(
                    request.form.get(
                        "branch"
                    )
                ),

            "account_number":
                clean(
                    request.form.get(
                        "account_number"
                    )
                ),

            "account_name":
                clean(
                    request.form.get(
                        "account_name"
                    )
                ),

            "status":
                "submitted",

            "created_at":
                utc_now(),
        }

        nrc_document = request.files.get(
            "nrc_document"
        )

        if (
            nrc_document
            and nrc_document.filename
        ):

            uploaded, error = upload_storage(
                nrc_document,
                "farmer-nrc",
            )

            if error:

                flash(
                    error,
                    "danger",
                )

                return redirect(
                    url_for("farmer")
                )

            data[
                "nrc_document_url"
            ] = uploaded["url"]

            data[
                "nrc_document_path"
            ] = uploaded["path"]

        row, error = db_insert(
            "farmer_registrations",
            data,
        )

        if error:

            logger.error(
                "Farmer registration failed: %s",
                error,
            )

            minimal = {
                "id":
                    data["id"],
                "user_id":
                    data["user_id"],
                "nrc":
                    data["nrc"],
                "first_name":
                    data["first_name"],
                "middle_names":
                    data["middle_names"],
                "last_name":
                    data["last_name"],
                "gender":
                    data["gender"],
                "phone":
                    data["phone"],
                "location":
                    data["location"],
            }

            row, error = db_insert(
                "farmer_registrations",
                minimal,
            )

        if error:

            logger.error(
                "Farmer fallback failed: %s",
                error,
            )

            flash(
                "Farmer registration could not be submitted. "
                "Check Render logs for the exact Supabase column error.",
                "danger",
            )

        else:

            flash(
                "Farmer registration submitted successfully.",
                "success",
            )

            log_activity(
                "farmer_registration",
                "Farmer registration submitted.",
            )

        return redirect(
            url_for("farmer")
        )

    return render_page(
        "Farmer Registration",
        r"""
        <div class="card">

            <h2>
                KOJA Farmer Registration
            </h2>

            <form
                method="POST"
                enctype="multipart/form-data"
            >

                <h3>
                    Personal Details
                </h3>

                <label>
                    NRC
                </label>

                <input name="nrc">

                <label>
                    Date of Birth
                </label>

                <input
                    type="date"
                    name="date_of_birth"
                >

                <label>
                    First Name
                </label>

                <input
                    name="first_name"
                    required
                >

                <label>
                    Middle Names
                </label>

                <input name="middle_names">

                <label>
                    Last Name
                </label>

                <input
                    name="last_name"
                    required
                >

                <label>
                    Gender
                </label>

                <select name="gender">

                    <option value="">
                        Select
                    </option>

                    <option value="Male">
                        Male
                    </option>

                    <option value="Female">
                        Female
                    </option>

                </select>

                <label>
                    Phone
                </label>

                <input name="phone">

                <label>
                    NRC Card
                </label>

                <input
                    type="file"
                    name="nrc_document"
                >

                <h3>
                    Farming Location
                </h3>

                <label>
                    Location
                </label>

                <input name="location">

                <h3>
                    Payment Details
                </h3>

                <label>
                    Payment Method
                </label>

                <select name="payment_method">

                    <option value="">
                        Select
                    </option>

                    <option value="Bank Account">
                        Bank Account
                    </option>

                    <option value="Mobile Money">
                        Mobile Money
                    </option>

                    <option value="Wallet">
                        Wallet
                    </option>

                </select>

                <label>
                    Provider
                </label>

                <input name="provider">

                <label>
                    Branch
                </label>

                <input name="branch">

                <label>
                    Account / Mobile Number
                </label>

                <input name="account_number">

                <label>
                    Account Name
                </label>

                <input name="account_name">

                <button type="submit">
                    Submit Farmer Registration
                </button>

            </form>

        </div>
        """,
    )


# ============================================================
# DOCTORS
# ============================================================

@app.route("/doctors")
@login_required
def doctors():

    doctors = db_select(
        "doctor_profiles",
        order="created_at.desc",
        limit=100,
    )

    return render_page(
        "Doctors",
        r"""
        <div class="card">

            <h2>
                Find a Doctor
            </h2>

            {% for d in doctors %}

                <div class="card">

                    <h3>
                        {{ d.get("full_name")
                           or
                           d.get("doctor_name")
                           or
                           "Doctor" }}
                    </h3>

                    <p>
                        <strong>
                            Specialty:
                        </strong>

                        {{ d.get("specialty")
                           or "General" }}
                    </p>

                    <p>
                        <strong>
                            Hospital/Clinic:
                        </strong>

                        {{ d.get("hospital_clinic")
                           or "Not specified" }}
                    </p>

                    {% if d.get("consultation_fee") %}

                        <p>
                            Fee:
                            {{ d.get("currency")
                               or "ZMW" }}
                            {{ d.get("consultation_fee") }}
                        </p>

                    {% endif %}

                    {% if d.get("provider_id") %}

                        <a
                            class="btn"
                            href="{{
                                url_for(
                                    'book_doctor',
                                    provider_id=d.get(
                                        'provider_id'
                                    )
                                )
                            }}"
                        >
                            Book This Doctor
                        </a>

                    {% endif %}

                </div>

            {% else %}

                <p>
                    No doctor profiles have been
                    registered yet.
                </p>

            {% endfor %}

        </div>
        """,
        doctors=doctors,
    )


@app.route(
    "/doctor/book/<provider_id>",
    methods=["GET", "POST"],
)
@login_required
def book_doctor(provider_id):

    user = current_user()

    doctor = first_row(
        "doctor_profiles",
        {
            "provider_id":
                provider_id
        },
    )

    if not doctor:
        abort(404)

    if request.method == "POST":

        payload = {
            "id":
                str(uuid.uuid4()),

            "client_id":
                user["id"],

            "provider_id":
                provider_id,

            "appointment_type":
                "doctor",

            "appointment_date":
                request.form.get(
                    "appointment_date"
                ),

            "start_time":
                request.form.get(
                    "start_time"
                ),

            "end_time":
                request.form.get(
                    "end_time"
                ),

            "location":
                clean(
                    request.form.get(
                        "location"
                    )
                ),

            "status":
                "requested",

            "notes":
                clean(
                    request.form.get(
                        "notes"
                    )
                ),

            "created_at":
                utc_now(),

            "updated_at":
                utc_now(),
        }

        row, error = db_insert(
            "appointments",
            payload,
        )

        if error:

            flash(
                "Appointment could not be created: "
                + str(error)[:600],
                "danger",
            )

        else:

            flash(
                "Doctor booking request submitted.",
                "success",
            )

        return redirect(
            url_for("dashboard")
        )

    return render_page(
        "Book Doctor",
        r"""
        <div class="card">

            <h2>
                Book
                {{ doctor.get("full_name")
                   or
                   doctor.get("doctor_name")
                   or "Doctor" }}
            </h2>

            <p>
                Specialty:
                {{ doctor.get("specialty")
                   or "General" }}
            </p>

            <form method="POST">

                <label>
                    Date
                </label>

                <input
                    type="date"
                    name="appointment_date"
                    required
                >

                <label>
                    Start Time
                </label>

                <input
                    type="time"
                    name="start_time"
                >

                <label>
                    End Time
                </label>

                <input
                    type="time"
                    name="end_time"
                >

                <label>
                    Location
                </label>

                <input name="location">

                <label>
                    Notes
                </label>

                <textarea
                    name="notes"
                ></textarea>

                <button type="submit">
                    Request Appointment
                </button>

            </form>

        </div>
        """,
        doctor=doctor,
    )


# ============================================================
# TEACHERS
# ============================================================

@app.route("/teachers")
@login_required
def teachers():

    teachers = db_select(
        "teacher_profiles",
        order="created_at.desc",
        limit=100,
    )

    return render_page(
        "Teachers",
        r"""
        <div class="card">

            <h2>
                Find a Teacher / Tutor
            </h2>

            {% for t in teachers %}

                <div class="card">

                    <h3>
                        {{ t.get("full_name")
                           or
                           t.get("teacher_name")
                           or "Teacher" }}
                    </h3>

                    <p>
                        <strong>
                            Subjects:
                        </strong>

                        {{ t.get("subjects")
                           or "Not specified" }}
                    </p>

                    <p>
                        <strong>
                            Grades:
                        </strong>

                        {{ t.get("grade_levels")
                           or "Not specified" }}
                    </p>

                    <p>
                        <strong>
                            Qualification:
                        </strong>

                        {{ t.get("qualification")
                           or "Not specified" }}
                    </p>

                    {% if t.get("hourly_rate") %}

                        <p>
                            Rate:
                            {{ t.get("currency")
                               or "ZMW" }}
                            {{ t.get("hourly_rate") }}/hour
                        </p>

                    {% endif %}

                    {% if t.get("provider_id") %}

                        <a
                            class="btn"
                            href="{{
                                url_for(
                                    'book_teacher',
                                    provider_id=t.get(
                                        'provider_id'
                                    )
                                )
                            }}"
                        >
                            Book Teacher
                        </a>

                    {% endif %}

                </div>

            {% else %}

                <p>
                    No teacher profiles have been
                    registered yet.
                </p>

            {% endfor %}

        </div>
        """,
        teachers=teachers,
    )


@app.route(
    "/teacher/book/<provider_id>",
    methods=["GET", "POST"],
)
@login_required
def book_teacher(provider_id):

    user = current_user()

    teacher = first_row(
        "teacher_profiles",
        {
            "provider_id":
                provider_id
        },
    )

    if not teacher:
        abort(404)

    if request.method == "POST":

        payload = {
            "id":
                str(uuid.uuid4()),

            "client_id":
                user["id"],

            "provider_id":
                provider_id,

            "appointment_type":
                "teacher",

            "appointment_date":
                request.form.get(
                    "appointment_date"
                ),

            "start_time":
                request.form.get(
                    "start_time"
                ),

            "end_time":
                request.form.get(
                    "end_time"
                ),

            "location":
                clean(
                    request.form.get(
                        "location"
                    )
                ),

            "status":
                "requested",

            "notes":
                clean(
                    request.form.get(
                        "notes"
                    )
                ),

            "created_at":
                utc_now(),

            "updated_at":
                utc_now(),
        }

        row, error = db_insert(
            "appointments",
            payload,
        )

        if error:

            flash(
                "Teacher booking failed: "
                + str(error)[:600],
                "danger",
            )

        else:

            flash(
                "Teacher booking request submitted.",
                "success",
            )

        return redirect(
            url_for("dashboard")
        )

    return render_page(
        "Book Teacher",
        r"""
        <div class="card">

            <h2>
                Book
                {{ teacher.get("full_name")
                   or
                   teacher.get("teacher_name")
                   or "Teacher" }}
            </h2>

            <p>
                {{ teacher.get("subjects")
                   or "" }}
            </p>

            <form method="POST">

                <label>
                    Date
                </label>

                <input
                    type="date"
                    name="appointment_date"
                    required
                >

                <label>
                    Start Time
                </label>

                <input
                    type="time"
                    name="start_time"
                >

                <label>
                    End Time
                </label>

                <input
                    type="time"
                    name="end_time"
                >

                <label>
                    Location / Online
                </label>

                <input name="location">

                <label>
                    Notes
                </label>

                <textarea
                    name="notes"
                ></textarea>

                <button type="submit">
                    Book Teacher
                </button>

            </form>

        </div>
        """,
        teacher=teacher,
    )


# ============================================================
# DRIVER REGISTRATION
#
# IMPORTANT:
# driver_profiles uses:
#
# id
# provider_id
# vehicle_type
# vehicle_make
# vehicle_model
# vehicle_registration
# driving_license_number
# service_area
# verification_status
# created_at
#
# ============================================================

@app.route(
    "/driver/register",
    methods=["GET", "POST"],
)
@app.route(
    "/drivers/register",
    methods=["GET", "POST"],
)
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
                "provider_id":
                    provider.get("id")
            },
        )

    if request.method == "POST":

        vehicle_type = clean(
            request.form.get(
                "vehicle_type"
            )
        )

        vehicle_make = clean(
            request.form.get(
                "vehicle_make"
            )
        )

        vehicle_model = clean(
            request.form.get(
                "vehicle_model"
            )
        )

        vehicle_registration = clean(
            request.form.get(
                "vehicle_registration"
            )
        )

        driving_license_number = clean(
            request.form.get(
                "driving_license_number"
            )
        )

        service_area = clean(
            request.form.get(
                "service_area"
            )
        )

        if not vehicle_type:
            flash(
                "Vehicle type is required.",
                "danger",
            )

            return redirect(
                url_for("driver_register")
            )

        if not vehicle_registration:
            flash(
                "Vehicle registration is required.",
                "danger",
            )

            return redirect(
                url_for("driver_register")
            )

        if not driving_license_number:
            flash(
                "Driving licence number is required.",
                "danger",
            )

            return redirect(
                url_for("driver_register")
            )

        provider, provider_error = (
            ensure_driver_provider(user)
        )

        if (
            provider_error
            or not provider
            or not provider.get("id")
        ):

            logger.error(
                "Driver provider creation failed: %s",
                provider_error,
            )

            flash(
                "Driver registration failed while creating "
                "the service provider record. "
                + str(
                    provider_error
                    or "Unknown database error"
                )[:800],
                "danger",
            )

            return redirect(
                url_for("driver_register")
            )

        provider_id = str(
            provider["id"]
        )

        existing = first_row(
            "driver_profiles",
            {
                "provider_id":
                    provider_id
            },
        )

        payload = {
            "provider_id":
                provider_id,

            "vehicle_type":
                vehicle_type,

            "vehicle_make":
                vehicle_make or None,

            "vehicle_model":
                vehicle_model or None,

            "vehicle_registration":
                vehicle_registration,

            "driving_license_number":
                driving_license_number,

            "service_area":
                service_area or None,

            "verification_status":
                "pending",
        }

        if existing and existing.get("id"):

            row, error = db_update(
                "driver_profiles",
                {
                    "id":
                        existing["id"]
                },
                payload,
            )

        else:

            payload["id"] = str(
                uuid.uuid4()
            )

            row, error = db_insert(
                "driver_profiles",
                payload,
            )

        if error:

            logger.error(
                "driver_profiles save failed: %s",
                error,
            )

            flash(
                "Driver registration failed: "
                + str(error)[:1000],
                "danger",
            )

            return redirect(
                url_for("driver_register")
            )

        # Update only columns we know are
        # present in profiles.
        profile_update = {
            "role": "driver"
        }

        _, profile_error = db_update(
            "profiles",
            {
                "id":
                    user["id"]
            },
            profile_update,
        )

        if profile_error:
            logger.warning(
                "Could not update profiles role: %s",
                profile_error,
            )

        session["user"]["role"] = "driver"

        session["user"][
            "driver_provider_id"
        ] = provider_id

        session["user"][
            "vehicle_type"
        ] = vehicle_type

        session["user"][
            "vehicle_number"
        ] = vehicle_registration

        log_activity(
            "driver_registration",
            "Driver profile submitted for verification.",
        )

        flash(
            "Driver registration submitted successfully. "
            "Your profile is pending admin verification.",
            "success",
        )

        return redirect(
            url_for("driver_dashboard")
        )

    return render_page(
        "Driver Registration",
        r"""
        <div class="card">

            <h2>
                Driver Registration
            </h2>

            <p>
                Complete your driver and vehicle
                information.
            </p>

            <form method="POST">

                <label>
                    Vehicle Type
                </label>

                <select
                    name="vehicle_type"
                    required
                >

                    <option value="">
                        Select vehicle type
                    </option>

                    <option value="Motorcycle">
                        Motorcycle
                    </option>

                    <option value="Car">
                        Car
                    </option>

                    <option value="Van">
                        Van
                    </option>

                    <option value="Pickup">
                        Pickup
                    </option>

                    <option value="Truck">
                        Truck
                    </option>

                    <option value="Bicycle">
                        Bicycle
                    </option>

                </select>

                <label>
                    Vehicle Make
                </label>

                <input
                    name="vehicle_make"
                >

                <label>
                    Vehicle Model
                </label>

                <input
                    name="vehicle_model"
                >

                <label>
                    Vehicle Registration
                </label>

                <input
                    name="vehicle_registration"
                    required
                >

                <label>
                    Driving Licence Number
                </label>

                <input
                    name="driving_license_number"
                    required
                >

                <label>
                    Service Area
                </label>

                <input
                    name="service_area"
                    placeholder="e.g. Kitwe CBD"
                >

                {% if existing %}

                    <p>
                        Current verification status:
                        <strong>
                            {{
                                existing.get(
                                    'verification_status'
                                )
                                or 'pending'
                            }}
                        </strong>
                    </p>

                {% endif %}

                <button type="submit">
                    Submit Driver Registration
                </button>

            </form>

        </div>
        """,
        existing=existing,
    )


# ============================================================
# DRIVER DASHBOARD
# ============================================================

@app.route("/driver")
@login_required
def driver_dashboard():

    user = current_user()

    if (
        user.get("role")
        not in ("driver", "admin")
        and not user.get("is_admin")
    ):

        return redirect(
            url_for("driver_register")
        )

    provider = get_driver_provider(
        user.get("id")
    )

    if not provider:

        return redirect(
            url_for("driver_register")
        )

    profile = first_row(
        "driver_profiles",
        {
            "provider_id":
                provider.get("id")
        },
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
        filters={
            "driver_id":
                provider_id
        },
        order="created_at.desc",
        limit=1,
    )

    latest = (
        locations[0]
        if locations
        else None
    )

    requests_rows = db_select(
        "deliveries",
        filters={
            "driver_id":
                provider_id
        },
        order="created_at.desc",
        limit=100,
    )

    return render_page(
        "Driver Dashboard",
        r"""
        <div class="card">

            <h2>
                Driver Dashboard
            </h2>

            <p>
                {{ user.name }}
            </p>

            <p>
                Vehicle:
                {{ profile.get("vehicle_type")
                   or "Vehicle" }}

                {{ profile.get(
                    "vehicle_registration"
                ) or "" }}
            </p>

            <p>
                Verification:
                <strong>
                    {{
                        profile.get(
                            "verification_status"
                        )
                        or "pending"
                    }}
                </strong>
            </p>

        </div>

        <div class="card">

            <h3>
                GPS / Availability
            </h3>

            <p>
                Current status:
                <strong>
                    {{
                        "ONLINE"
                        if latest
                        and latest.get("is_online")
                        else "OFFLINE"
                    }}
                </strong>
            </p>

            <a
                class="btn btn-green"
                href="{{ url_for('tracking') }}"
            >
                Open GPS & Go Online
            </a>

            <button
                class="btn btn-red"
                onclick="goOffline()"
            >
                Go Offline
            </button>

        </div>

        <div class="card">

            <h3>
                Delivery Requests / Jobs
            </h3>

            {% for d in requests_rows %}

                <div class="card">

                    <strong>
                        {{ d.get("tracking_code")
                           or "Delivery" }}
                    </strong>

                    <p>
                        {{ d.get("pickup_location")
                           or "" }}

                        →

                        {{ d.get("destination")
                           or "" }}
                    </p>

                    <p>
                        Status:
                        <strong>
                            {{
                                d.get("status")
                                or "requested"
                            }}
                        </strong>
                    </p>

                    {% if d.get("status")
                        == "requested" %}

                        <form
                            method="POST"
                            action="{{
                                url_for(
                                    'driver_delivery_action',
                                    delivery_id=d.get(
                                        'id'
                                    ),
                                    action='accept'
                                )
                            }}"
                            style="display:inline"
                        >

                            <button
                                class="btn btn-green"
                            >
                                Accept
                            </button>

                        </form>

                        <form
                            method="POST"
                            action="{{
                                url_for(
                                    'driver_delivery_action',
                                    delivery_id=d.get(
                                        'id'
                                    ),
                                    action='reject'
                                )
                            }}"
                            style="display:inline"
                        >

                            <button
                                class="btn btn-red"
                            >
                                Reject
                            </button>

                        </form>

                    {% elif d.get("status")
                          == "accepted" %}

                        <form
                            method="POST"
                            action="{{
                                url_for(
                                    'driver_delivery_action',
                                    delivery_id=d.get(
                                        'id'
                                    ),
                                    action='picked_up'
                                )
                            }}"
                            style="display:inline"
                        >

                            <button class="btn">
                                Picked Up
                            </button>

                        </form>

                    {% elif d.get("status")
                          == "picked_up" %}

                        <form
                            method="POST"
                            action="{{
                                url_for(
                                    'driver_delivery_action',
                                    delivery_id=d.get(
                                        'id'
                                    ),
                                    action='in_transit'
                                )
                            }}"
                            style="display:inline"
                        >

                            <button class="btn">
                                In Transit
                            </button>

                        </form>

                    {% elif d.get("status")
                          == "in_transit" %}

                        <form
                            method="POST"
                            action="{{
                                url_for(
                                    'driver_delivery_action',
                                    delivery_id=d.get(
                                        'id'
                                    ),
                                    action='delivered'
                                )
                            }}"
                            style="display:inline"
                        >

                            <button
                                class="btn btn-green"
                            >
                                Delivered
                            </button>

                        </form>

                    {% endif %}

                    {% if d.get("tracking_code") %}

                        <a
                            class="btn btn-dark"
                            href="{{
                                url_for(
                                    'track_delivery',
                                    tracking_code=d.get(
                                        'tracking_code'
                                    )
                                )
                            }}"
                        >
                            Track Map
                        </a>

                    {% endif %}

                </div>

            {% else %}

                <p>
                    No delivery requests yet.
                </p>

            {% endfor %}

        </div>

        <script>
        async function goOffline() {

            try {

                const response =
                    await fetch(
                        "{{ url_for(
                            'driver_offline'
                        ) }}",
                        {
                            method: "POST",
                            headers: {
                                "Content-Type":
                                    "application/json"
                            }
                        }
                    );

                const data =
                    await response.json();

                alert(
                    data.message
                    || "Driver is offline."
                );

                location.reload();

            } catch (error) {

                alert(
                    "Could not go offline."
                );

            }
        }
        </script>
        """,
        profile=profile,
        latest=latest,
        requests_rows=requests_rows,
    )


# ============================================================
# DRIVER DELIVERY ACTION
#
# FIXED:
# Original code had:
# @app.route("/driver/delivery/<delivery_id>/")
# def function(delivery_id, action)
#
# but action was not in the URL.
#
# ============================================================

@app.route(
    "/driver/delivery/<delivery_id>/<action>",
    methods=["POST"],
)
@driver_required
def driver_delivery_action(
    delivery_id,
    action,
):

    user = current_user()

    provider = get_driver_provider(
        user.get("id")
    )

    if not provider:

        flash(
            "Driver provider record not found.",
            "danger",
        )

        return redirect(
            url_for("driver_register")
        )

    provider_id = str(
        provider["id"]
    )

    delivery = first_row(
        "deliveries",
        {
            "id":
                delivery_id
        },
    )

    if not delivery:
        abort(404)

    allowed_actions = {
        "accept": "accepted",
        "reject": "rejected",
        "picked_up": "picked_up",
        "in_transit": "in_transit",
        "delivered": "delivered",
    }

    if action not in allowed_actions:
        abort(400)

    assigned = delivery.get(
        "driver_id"
    )

    if action == "accept":

        if (
            assigned
            and str(assigned)
            != provider_id
        ):

            flash(
                "This delivery is assigned to another driver.",
                "danger",
            )

            return redirect(
                url_for("driver_dashboard")
            )

    else:

        if (
            assigned
            and str(assigned)
            != provider_id
        ):

            flash(
                "This delivery is assigned to another driver.",
                "danger",
            )

            return redirect(
                url_for("driver_dashboard")
            )

    status = allowed_actions[
        action
    ]

    payload = {
        "status":
            status,
        "updated_at":
            utc_now(),
    }

    if action == "accept":
        payload[
            "driver_id"
        ] = provider_id

    row, error = db_update(
        "deliveries",
        {
            "id":
                delivery_id
        },
        payload,
    )

    if error:

        flash(
            "Could not update delivery status: "
            + str(error)[:800],
            "danger",
        )

    else:

        log_activity(
            "delivery_status",
            (
                f"Delivery "
                f"{delivery.get('tracking_code')} "
                f"changed to {status}."
            ),
        )

        flash(
            f"Delivery status changed to {status}.",
            "success",
        )

    return redirect(
        url_for("driver_dashboard")
    )


# ============================================================
# DRIVER GPS PAGE
# ============================================================

@app.route("/tracking")
@login_required
def tracking():

    return render_page(
        "Live GPS Tracking",
        r"""
        <div class="card">

            <h2>
                Live Driver GPS
            </h2>

            <p>
                Allow browser location permission.
                Keep this page open while driving.
            </p>

            <label>
                Delivery ID (optional)
            </label>

            <input
                id="deliveryId"
                placeholder="Delivery UUID"
            >

            <button
                class="btn btn-green"
                onclick="startGPS()"
            >
                Go Online / Start GPS
            </button>

            <button
                class="btn btn-red"
                onclick="stopGPS()"
            >
                Stop GPS / Go Offline
            </button>

            <div class="card">

                <h3>
                    GPS Status
                </h3>

                <p id="status">
                    GPS not started.
                </p>

                <p id="coordinates">
                    -
                </p>

            </div>

        </div>

        <script>

        let watchId = null;

        async function sendLocation(position) {

            const deliveryId =
                document.getElementById(
                    "deliveryId"
                ).value.trim();

            const payload = {
                latitude:
                    position.coords.latitude,

                longitude:
                    position.coords.longitude,

                accuracy:
                    position.coords.accuracy,

                speed:
                    position.coords.speed,

                heading:
                    position.coords.heading
            };

            if (deliveryId) {
                payload.delivery_id =
                    deliveryId;
            }

            try {

                const response =
                    await fetch(
                        "{{ url_for(
                            'driver_location_update'
                        ) }}",
                        {
                            method: "POST",

                            headers: {
                                "Content-Type":
                                    "application/json"
                            },

                            body:
                                JSON.stringify(
                                    payload
                                )
                        }
                    );

                const data =
                    await response.json();

                if (!data.ok) {

                    document.getElementById(
                        "status"
                    ).innerText =
                        data.message
                        || "GPS error.";

                    return;
                }

                document.getElementById(
                    "status"
                ).innerText =
                    "ONLINE — GPS location saved.";

                document.getElementById(
                    "coordinates"
                ).innerText =
                    data.latitude
                    + ", "
                    + data.longitude;

            } catch (error) {

                document.getElementById(
                    "status"
                ).innerText =
                    "Could not send GPS location.";

            }
        }


        function gpsError(error) {

            document.getElementById(
                "status"
            ).innerText =
                "GPS error: "
                + error.message;
        }


        function startGPS() {

            if (!navigator.geolocation) {

                alert(
                    "This browser does not support GPS."
                );

                return;
            }

            if (watchId !== null) {
                return;
            }

            document.getElementById(
                "status"
            ).innerText =
                "Starting GPS...";

            watchId =
                navigator.geolocation.watchPosition(
                    sendLocation,
                    gpsError,
                    {
                        enableHighAccuracy: true,
                        maximumAge: 5000,
                        timeout: 20000
                    }
                );
        }


        async function stopGPS() {

            if (watchId !== null) {

                navigator.geolocation.clearWatch(
                    watchId
                );

                watchId = null;
            }

            try {

                const response =
                    await fetch(
                        "{{ url_for(
                            'driver_offline'
                        ) }}",
                        {
                            method: "POST",
                            headers: {
                                "Content-Type":
                                    "application/json"
                            }
                        }
                    );

                const data =
                    await response.json();

                document.getElementById(
                    "status"
                ).innerText =
                    data.message
                    || "Offline.";

            } catch (error) {

                document.getElementById(
                    "status"
                ).innerText =
                    "GPS stopped.";

            }
        }

        </script>
        """,
    )


# ============================================================
# SAVE DRIVER GPS LOCATION
# ============================================================

@app.route(
    "/api/driver/location",
    methods=["POST"],
)
@driver_required
def driver_location_update():

    if not table_exists(
        "driver_locations"
    ):

        return jsonify({
            "ok": False,
            "message":
                "driver_locations table is not available.",
        }), 503

    user = current_user()

    provider = get_driver_provider(
        user.get("id")
    )

    if not provider:

        return jsonify({
            "ok": False,
            "message":
                "Driver provider profile not found.",
        }), 404

    provider_id = str(
        provider["id"]
    )

    body = request.get_json(
        silent=True
    ) or {}

    latitude = safe_float(
        body.get("latitude")
    )

    longitude = safe_float(
        body.get("longitude")
    )

    if (
        latitude is None
        or longitude is None
        or not -90 <= latitude <= 90
        or not -180 <= longitude <= 180
    ):

        return jsonify({
            "ok": False,
            "message":
                "Invalid latitude or longitude.",
        }), 400

    payload = {
        "id":
            str(uuid.uuid4()),

        "driver_id":
            provider_id,

        "latitude":
            latitude,

        "longitude":
            longitude,

        "accuracy":
            safe_float(
                body.get("accuracy")
            ),

        "speed":
            safe_float(
                body.get("speed")
            ),

        "heading":
            safe_float(
                body.get("heading")
            ),

        "is_online":
            True,

        "created_at":
            utc_now(),
    }

    row, error = db_insert(
        "driver_locations",
        payload,
    )

    if error:

        logger.error(
            "driver_locations insert failed: %s",
            error,
        )

        return jsonify({
            "ok": False,
            "message":
                "GPS location could not be saved.",
            "error":
                str(error)[:800],
        }), 500

    delivery_id = clean(
        body.get("delivery_id")
    )

    if delivery_id:

        delivery = first_row(
            "deliveries",
            {
                "id":
                    delivery_id
            },
        )

        if delivery:

            assigned_driver = str(
                delivery.get("driver_id")
                or ""
            )

            if (
                not assigned_driver
                or assigned_driver
                == provider_id
            ):

                db_update(
                    "deliveries",
                    {
                        "id":
                            delivery_id
                    },
                    {
                        "driver_id":
                            provider_id,
                        "updated_at":
                            utc_now(),
                    },
                )

    return jsonify({
        "ok": True,
        "latitude": latitude,
        "longitude": longitude,
        "created_at": utc_now(),
    })


# ============================================================
# DRIVER OFFLINE
# ============================================================

@app.route(
    "/api/driver/offline",
    methods=["POST"],
)
@driver_required
def driver_offline():

    user = current_user()

    provider = get_driver_provider(
        user.get("id")
    )

    if not provider:

        return jsonify({
            "ok": False,
            "message":
                "Driver provider profile not found.",
        }), 404

    provider_id = str(
        provider["id"]
    )

    locations = db_select(
        "driver_locations",
        filters={
            "driver_id":
                provider_id
        },
        order="created_at.desc",
        limit=1,
    )

    latest = (
        locations[0]
        if locations
        else None
    )

    payload = {
        "id":
            str(uuid.uuid4()),

        "driver_id":
            provider_id,

        "latitude":
            latest.get("latitude")
            if latest else None,

        "longitude":
            latest.get("longitude")
            if latest else None,

        "accuracy":
            latest.get("accuracy")
            if latest else None,

        "speed":
            None,

        "heading":
            None,

        "is_online":
            False,

        "created_at":
            utc_now(),
    }

    row, error = db_insert(
        "driver_locations",
        payload,
    )

    if error:

        return jsonify({
            "ok": False,
            "message":
                "Could not mark driver offline.",
            "error":
                str(error)[:800],
        }), 500

    return jsonify({
        "ok": True,
        "message":
            "Driver is now offline.",
    })


# ============================================================
# NEARBY DRIVERS
# ============================================================

@app.route("/drivers")
@login_required
def drivers():

    return render_page(
        "Nearby Drivers",
        r"""
        <div class="card">

            <h2>
                Nearby Delivery Drivers
            </h2>

            <p>
                Allow location access to find
                online drivers around your
                pickup/shop location.
            </p>

            <label>
                Your Latitude
            </label>

            <input
                id="latitude"
                type="number"
                step="any"
            >

            <label>
                Your Longitude
            </label>

            <input
                id="longitude"
                type="number"
                step="any"
            >

            <label>
                Search Radius (km)
            </label>

            <input
                id="radius"
                type="number"
                value="50"
                min="1"
                max="200"
            >

            <button
                class="btn btn-dark"
                onclick="useMyLocation()"
            >
                Use My Current Location
            </button>

            <button
                class="btn"
                onclick="findDrivers()"
            >
                Find Nearby Drivers
            </button>

        </div>

        <div
            class="card"
            id="results"
        >

            <h3>
                Available Drivers
            </h3>

            <p>
                Enter your location and search.
            </p>

        </div>

        <script>

        function useMyLocation() {

            if (!navigator.geolocation) {

                alert(
                    "GPS is not supported."
                );

                return;
            }

            navigator.geolocation.getCurrentPosition(
                function(position) {

                    document.getElementById(
                        "latitude"
                    ).value =
                        position.coords.latitude;

                    document.getElementById(
                        "longitude"
                    ).value =
                        position.coords.longitude;

                    findDrivers();

                },

                function(error) {

                    alert(
                        "Location error: "
                        + error.message
                    );

                },

                {
                    enableHighAccuracy: true,
                    timeout: 20000
                }
            );
        }


        async function findDrivers() {

            const latitude =
                document.getElementById(
                    "latitude"
                ).value;

            const longitude =
                document.getElementById(
                    "longitude"
                ).value;

            const radius =
                document.getElementById(
                    "radius"
                ).value;

            if (!latitude || !longitude) {

                alert(
                    "Please provide your location."
                );

                return;
            }

            const url =
                "{{ url_for(
                    'nearby_drivers'
                ) }}"
                + "?latitude="
                + encodeURIComponent(latitude)
                + "&longitude="
                + encodeURIComponent(longitude)
                + "&radius_km="
                + encodeURIComponent(radius);

            try {

                const response =
                    await fetch(url);

                const data =
                    await response.json();

                if (!data.ok) {

                    document.getElementById(
                        "results"
                    ).innerHTML =
                        "<p>"
                        + (
                            data.message
                            || "Search failed."
                        )
                        + "</p>";

                    return;
                }

                const drivers =
                    data.drivers || [];

                if (!drivers.length) {

                    document.getElementById(
                        "results"
                    ).innerHTML =
                        "<h3>"
                        + "Available Drivers"
                        + "</h3>"
                        + "<p>"
                        + "No online drivers were found "
                        + "within the selected radius."
                        + "</p>";

                    return;
                }

                let html =
                    "<h3>"
                    + "Available Drivers"
                    + "</h3>";

                drivers.forEach(
                    function(driver) {

                        html +=
                            '<div class="card">';

                        html +=
                            "<h3>"
                            + escapeHtml(
                                driver.name
                            )
                            + "</h3>";

                        html +=
                            "<p>"
                            + "<strong>Vehicle:</strong> "
                            + escapeHtml(
                                driver.vehicle_type
                                || "Vehicle"
                            )
                            + "</p>";

                        html +=
                            "<p>"
                            + "<strong>Registration:</strong> "
                            + escapeHtml(
                                driver.vehicle_registration
                                || ""
                            )
                            + "</p>";

                        html +=
                            "<p>"
                            + "<strong>Distance:</strong> "
                            + driver.distance_km
                            + " km"
                            + "</p>";

                        html +=
                            '<button class="btn btn-green" '
                            + 'onclick="requestDriver(\''
                            + driver.driver_id
                            + '\')">'
                            + "Send Delivery Request"
                            + "</button>";

                        html +=
                            "</div>";
                    }
                );

                document.getElementById(
                    "results"
                ).innerHTML = html;

            } catch (error) {

                alert(
                    "Could not find drivers."
                );

            }
        }


        async function requestDriver(
            driverId
        ) {

            const pickup =
                prompt(
                    "Enter pickup/shop location:"
                );

            if (!pickup) {
                return;
            }

            const destination =
                prompt(
                    "Enter destination:"
                );

            if (!destination) {
                return;
            }

            const recipient =
                prompt(
                    "Recipient name:"
                ) || "";

            const phone =
                prompt(
                    "Recipient phone:"
                ) || "";

            const description =
                prompt(
                    "Package description:"
                ) || "";

            const latitude =
                document.getElementById(
                    "latitude"
                ).value;

            const longitude =
                document.getElementById(
                    "longitude"
                ).value;

            try {

                const response =
                    await fetch(
                        "{{ url_for(
                            'create_delivery_request'
                        ) }}",
                        {
                            method: "POST",

                            headers: {
                                "Content-Type":
                                    "application/json"
                            },

                            body:
                                JSON.stringify({
                                    driver_id:
                                        driverId,

                                    pickup_location:
                                        pickup,

                                    destination:
                                        destination,

                                    pickup_latitude:
                                        latitude,

                                    pickup_longitude:
                                        longitude,

                                    recipient_name:
                                        recipient,

                                    recipient_phone:
                                        phone,

                                    package_description:
                                        description
                                })
                        }
                    );

                const data =
                    await response.json();

                alert(
                    data.message
                    || "Delivery request sent."
                );

            } catch (error) {

                alert(
                    "Could not send delivery request."
                );

            }
        }


        function escapeHtml(value) {

            return String(value || "")
                .replace(
                    /&/g,
                    "&amp;"
                )
                .replace(
                    /</g,
                    "&lt;"
                )
                .replace(
                    />/g,
                    "&gt;"
                )
                .replace(
                    /"/g,
                    "&quot;"
                )
                .replace(
                    /'/g,
                    "&#039;"
                );
        }

        </script>
        """,
    )


@app.route("/api/nearby-drivers")
@login_required
def nearby_drivers():

    latitude = safe_float(
        request.args.get(
            "latitude"
        )
    )

    longitude = safe_float(
        request.args.get(
            "longitude"
        )
    )

    radius = (
        safe_float(
            request.args.get(
                "radius_km"
            )
        )
        or 50
    )

    radius = max(
        1,
        min(radius, 200),
    )

    if (
        latitude is None
        or longitude is None
        or not -90 <= latitude <= 90
        or not -180 <= longitude <= 180
    ):

        return jsonify({
            "ok": False,
            "message":
                "Valid latitude and longitude are required.",
        }), 400

    if not table_exists(
        "driver_locations"
    ):

        return jsonify({
            "ok": False,
            "message":
                "The driver_locations table is not installed.",
        }), 503

    latest = latest_driver_locations()

    results = []

    now = datetime.now(
        timezone.utc
    )

    for driver_id, location in latest.items():

        if not location.get(
            "is_online"
        ):
            continue

        driver_latitude = safe_float(
            location.get(
                "latitude"
            )
        )

        driver_longitude = safe_float(
            location.get(
                "longitude"
            )
        )

        if (
            driver_latitude is None
            or driver_longitude is None
        ):
            continue

        created = location.get(
            "created_at"
        )

        if created:

            try:

                created_dt = (
                    datetime.fromisoformat(
                        str(created).replace(
                            "Z",
                            "+00:00",
                        )
                    )
                )

                age_seconds = (
                    now - created_dt
                ).total_seconds()

                if age_seconds > 600:
                    continue

            except Exception:
                pass

        distance = haversine_km(
            latitude,
            longitude,
            driver_latitude,
            driver_longitude,
        )

        if distance > radius:
            continue

        profile = first_row(
            "driver_profiles",
            {
                "provider_id":
                    driver_id
            },
        )

        provider = first_row(
            "service_providers",
            {
                "id":
                    driver_id
            },
        ) or {}

        results.append({
            "driver_id":
                str(driver_id),

            "name":
                first_nonempty(
                    provider.get(
                        "full_name"
                    ),
                    provider.get(
                        "name"
                    ),
                    "Driver",
                ),

            "phone":
                first_nonempty(
                    provider.get(
                        "phone"
                    )
                ),

            "vehicle_type":
                first_nonempty(
                    profile.get(
                        "vehicle_type"
                    )
                    if profile
                    else ""
                ),

            "vehicle_registration":
                first_nonempty(
                    profile.get(
                        "vehicle_registration"
                    )
                    if profile
                    else ""
                ),

            "latitude":
                driver_latitude,

            "longitude":
                driver_longitude,

            "accuracy":
                location.get(
                    "accuracy"
                ),

            "distance_km":
                round(
                    distance,
                    2,
                ),

            "updated_at":
                location.get(
                    "created_at"
                ),
        })

    results.sort(
        key=lambda item:
            item["distance_km"]
    )

    return jsonify({
        "ok": True,
        "drivers": results,
    })


# ============================================================
# DELIVERY HELPERS
# ============================================================

def make_tracking_code():

    return (
        "KOJA-"
        + datetime.now().strftime(
            "%Y%m%d"
        )
        + "-"
        + secrets.token_hex(
            3
        ).upper()
    )


# ============================================================
# CREATE DELIVERY REQUEST
# ============================================================

@app.route(
    "/api/delivery/request",
    methods=["POST"],
)
@login_required
def create_delivery_request():

    user = current_user()

    body = request.get_json(
        silent=True
    ) or {}

    driver_id = clean(
        body.get(
            "driver_id"
        )
    )

    if not driver_id:

        return jsonify({
            "ok": False,
            "message":
                "Select a driver first.",
        }), 400

    driver = first_row(
        "driver_profiles",
        {
            "provider_id":
                driver_id
        },
    )

    if not driver:

        return jsonify({
            "ok": False,
            "message":
                "Driver profile not found.",
        }), 404

    pickup_latitude = safe_float(
        body.get(
            "pickup_latitude"
        )
    )

    pickup_longitude = safe_float(
        body.get(
            "pickup_longitude"
        )
    )

    tracking = make_tracking_code()

    payload = {
        "id":
            str(uuid.uuid4()),

        "customer_id":
            user["id"],

        "user_id":
            user["id"],

        "driver_id":
            driver_id,

        "pickup_location":
            clean(
                body.get(
                    "pickup_location"
                )
            ),

        "destination":
            clean(
                body.get(
                    "destination"
                )
            ),

        "pickup_latitude":
            pickup_latitude,

        "pickup_longitude":
            pickup_longitude,

        "recipient_name":
            clean(
                body.get(
                    "recipient_name"
                )
            ),

        "recipient_phone":
            clean(
                body.get(
                    "recipient_phone"
                )
            ),

        "package_description":
            clean(
                body.get(
                    "package_description"
                )
            ),

        "package_weight":
            body.get(
                "package_weight"
            ),

        "delivery_fee":
            body.get(
                "delivery_fee"
            )
            or 0,

        "currency":
            "ZMW",

        "status":
            "requested",

        "tracking_code":
            tracking,

        "notes":
            clean(
                body.get(
                    "notes"
                )
            ),

        "created_at":
            utc_now(),

        "updated_at":
            utc_now(),
    }

    row, error = db_insert(
        "deliveries",
        payload,
    )

    if error:

        logger.error(
            "Delivery full insert failed: %s",
            error,
        )

        minimal = {
            "id":
                payload["id"],

            "customer_id":
                user["id"],

            "driver_id":
                driver_id,

            "pickup_location":
                payload[
                    "pickup_location"
                ],

            "destination":
                payload[
                    "destination"
                ],

            "recipient_name":
                payload[
                    "recipient_name"
                ],

            "recipient_phone":
                payload[
                    "recipient_phone"
                ],

            "package_description":
                payload[
                    "package_description"
                ],

            "status":
                "requested",

            "tracking_code":
                tracking,
        }

        row, error = db_insert(
            "deliveries",
            minimal,
        )

    if error:

        return jsonify({
            "ok": False,
            "message":
                "Delivery request could not be created.",
            "error":
                str(error)[:800],
        }), 500

    log_activity(
        "delivery_requested",
        (
            f"Delivery {tracking} "
            f"requested from driver "
            f"{driver_id}."
        ),
    )

    return jsonify({
        "ok": True,
        "tracking_code":
            tracking,
        "message":
            (
                "Delivery request sent to the driver. "
                f"Tracking code: {tracking}."
            ),
    })


# ============================================================
# DELIVERIES PAGE
# ============================================================

@app.route(
    "/deliveries",
    methods=["GET", "POST"],
)
@login_required
def deliveries():

    user = current_user()

    if request.method == "POST":

        tracking = make_tracking_code()

        payload = {
            "id":
                str(uuid.uuid4()),

            "customer_id":
                user["id"],

            "pickup_location":
                clean(
                    request.form.get(
                        "pickup_location"
                    )
                ),

            "destination":
                clean(
                    request.form.get(
                        "destination"
                    )
                ),

            "recipient_name":
                clean(
                    request.form.get(
                        "recipient_name"
                    )
                ),

            "recipient_phone":
                clean(
                    request.form.get(
                        "recipient_phone"
                    )
                ),

            "package_description":
                clean(
                    request.form.get(
                        "package_description"
                    )
                ),

            "package_weight":
                request.form.get(
                    "package_weight"
                ) or None,

            "delivery_fee":
                request.form.get(
                    "delivery_fee"
                ) or 0,

            "currency":
                "ZMW",

            "requested_date":
                request.form.get(
                    "requested_date"
                ) or None,

            "requested_time":
                request.form.get(
                    "requested_time"
                ) or None,

            "status":
                "requested",

            "tracking_code":
                tracking,

            "notes":
                clean(
                    request.form.get(
                        "notes"
                    )
                ),

            "created_at":
                utc_now(),

            "updated_at":
                utc_now(),
        }

        row, error = db_insert(
            "deliveries",
            payload,
        )

        if error:

            flash(
                "Delivery could not be registered: "
                + str(error)[:700],
                "danger",
            )

        else:

            flash(
                (
                    "Delivery registered. "
                    f"Tracking code: {tracking}. "
                    "Now choose a nearby driver."
                ),
                "success",
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
            "customer_id":
                user["id"]
        },
        order="created_at.desc",
        limit=100,
    )

    return render_page(
        "Deliveries",
        r"""
        <div class="card">

            <h2>
                Delivery Service
            </h2>

            <p>
                Use Nearby Drivers to see
                drivers around your
                pickup/shop location.
            </p>

            <a
                class="btn"
                href="{{ url_for('drivers') }}"
            >
                Find Nearby Drivers
            </a>

        </div>

        <div class="card">

            <h2>
                Create Delivery Without
                Selecting Driver Yet
            </h2>

            <form method="POST">

                <label>
                    Pickup / Shop Location
                </label>

                <input
                    name="pickup_location"
                    required
                >

                <label>
                    Destination
                </label>

                <input
                    name="destination"
                    required
                >

                <label>
                    Recipient Name
                </label>

                <input
                    name="recipient_name"
                >

                <label>
                    Recipient Phone
                </label>

                <input
                    name="recipient_phone"
                >

                <label>
                    Package Description
                </label>

                <textarea
                    name="package_description"
                ></textarea>

                <label>
                    Package Weight (kg)
                </label>

                <input
                    type="number"
                    step="0.01"
                    name="package_weight"
                >

                <label>
                    Delivery Fee (ZMW)
                </label>

                <input
                    type="number"
                    step="0.01"
                    name="delivery_fee"
                >

                <label>
                    Requested Date
                </label>

                <input
                    type="date"
                    name="requested_date"
                >

                <label>
                    Requested Time
                </label>

                <input
                    type="time"
                    name="requested_time"
                >

                <label>
                    Notes
                </label>

                <textarea
                    name="notes"
                ></textarea>

                <button type="submit">
                    Create Delivery Request
                </button>

            </form>

        </div>

        <div class="card">

            <h2>
                My Deliveries
            </h2>

            {% for d in rows %}

                <div class="card">

                    <strong>
                        {{ d.get("tracking_code")
                           or "Delivery" }}
                    </strong>

                    <p>
                        {{ d.get("pickup_location")
                           or "" }}

                        →

                        {{ d.get("destination")
                           or "" }}
                    </p>

                    <p>
                        Status:
                        {{ d.get("status")
                           or "requested" }}
                    </p>

                    <p>
                        Driver:
                        {{
                            d.get("driver_id")
                            or "Not selected"
                        }}
                    </p>

                    {% if d.get("tracking_code") %}

                        <a
                            class="btn"
                            href="{{
                                url_for(
                                    'track_delivery',
                                    tracking_code=d.get(
                                        'tracking_code'
                                    )
                                )
                            }}"
                        >
                            Track Delivery
                        </a>

                    {% endif %}

                    {% if not d.get("driver_id") %}

                        <a
                            class="btn btn-green"
                            href="{{
                                url_for('drivers')
                            }}"
                        >
                            Find Driver
                        </a>

                    {% endif %}

                </div>

            {% else %}

                <p>
                    No deliveries registered.
                </p>

            {% endfor %}

        </div>
        """,
        rows=rows,
    )


# ============================================================
# DELIVERY TRACKING
# ============================================================

@app.route(
    "/track/<tracking_code>"
)
@login_required
def track_delivery(
    tracking_code
):

    delivery = first_row(
        "deliveries",
        {
            "tracking_code":
                tracking_code
        },
    )

    if not delivery:
        abort(404)

    return render_page(
        "Track Delivery",
        r"""
        <div class="card">

            <h2>
                Delivery Tracking
            </h2>

            <p>
                Tracking code:
                <strong>
                    {{ delivery.get(
                        "tracking_code"
                    ) }}
                </strong>
            </p>

            <p>
                Pickup:
                {{ delivery.get(
                    "pickup_location"
                ) }}
            </p>

            <p>
                Destination:
                {{ delivery.get(
                    "destination"
                ) }}
            </p>

            <p>
                Status:
                <strong id="status">
                    {{ delivery.get(
                        "status"
                    ) }}
                </strong>
            </p>

            <p id="location">
                Waiting for driver's location...
            </p>

            <div
                id="mapLink"
            ></div>

        </div>

        <script>

        async function updateLocation() {

            try {

                const response =
                    await fetch(
                        "{{ url_for(
                            'delivery_location',
                            tracking_code=delivery.get(
                                'tracking_code'
                            )
                        ) }}"
                    );

                const data =
                    await response.json();

                if (!data.ok) {

                    document.getElementById(
                        "location"
                    ).innerText =
                        data.message
                        || "No GPS location.";

                    return;
                }

                document.getElementById(
                    "status"
                ).innerText =
                    data.status || "";

                document.getElementById(
                    "location"
                ).innerText =
                    "Driver location: "
                    + data.latitude
                    + ", "
                    + data.longitude;

                const mapUrl =
                    "https://www.google.com/maps/search/?api=1"
                    + "&query="
                    + encodeURIComponent(
                        data.latitude
                        + ","
                        + data.longitude
                    );

                document.getElementById(
                    "mapLink"
                ).innerHTML =
                    '<a class="btn" '
                    + 'target="_blank" '
                    + 'href="'
                    + mapUrl
                    + '">'
                    + "Open Driver on Map"
                    + "</a>";

            } catch (error) {

                console.log(error);

            }
        }

        updateLocation();

        setInterval(
            updateLocation,
            10000
        );

        </script>
        """,
        delivery=delivery,
    )


@app.route(
    "/api/delivery/<tracking_code>/location"
)
@login_required
def delivery_location(
    tracking_code
):

    delivery = first_row(
        "deliveries",
        {
            "tracking_code":
                tracking_code
        },
    )

    if not delivery:

        return jsonify({
            "ok": False,
            "message":
                "Delivery not found.",
        }), 404

    driver_id = delivery.get(
        "driver_id"
    )

    if not driver_id:

        return jsonify({
            "ok": False,
            "message":
                "No driver has been assigned yet.",
            "status":
                delivery.get(
                    "status"
                ),
        })

    locations = db_select(
        "driver_locations",
        filters={
            "driver_id":
                driver_id
        },
        order="created_at.desc",
        limit=1,
    )

    if not locations:

        return jsonify({
            "ok": False,
            "message":
                "Driver has not shared a GPS location yet.",
            "status":
                delivery.get(
                    "status"
                ),
        })

    location = locations[0]

    return jsonify({
        "ok": True,

        "latitude":
            location.get(
                "latitude"
            ),

        "longitude":
            location.get(
                "longitude"
            ),

        "accuracy":
            location.get(
                "accuracy"
            ),

        "speed":
            location.get(
                "speed"
            ),

        "heading":
            location.get(
                "heading"
            ),

        "updated_at":
            location.get(
                "created_at"
            ),

        "status":
            delivery.get(
                "status"
            ),
    })


# ============================================================
# PROVIDER LOCATION
# ============================================================

@app.route(
    "/provider-map/<provider_id>"
)
@login_required
def provider_map(
    provider_id
):

    provider_type = request.args.get(
        "provider_type",
        "provider",
    )

    return render_page(
        "Provider Location",
        r"""
        <div class="card">

            <h2>
                {{ provider_type|title }}
                Location
            </h2>

            <p>
                Latest GPS position.
            </p>

            <p id="location">
                Loading provider location...
            </p>

        </div>

        <script>

        async function loadProviderLocation() {

            try {

                const response =
                    await fetch(
                        "{{ url_for(
                            'provider_location',
                            provider_id=provider_id
                        ) }}"
                    );

                const data =
                    await response.json();

                if (!data.ok) {

                    document.getElementById(
                        "location"
                    ).innerText =
                        data.message
                        || "No location.";

                    return;
                }

                document.getElementById(
                    "location"
                ).innerText =
                    data.latitude
                    + ", "
                    + data.longitude;

            } catch (error) {

                document.getElementById(
                    "location"
                ).innerText =
                    "Unable to load location.";

            }
        }

        loadProviderLocation();

        </script>
        """,
        provider_id=provider_id,
        provider_type=provider_type,
    )


@app.route(
    "/api/provider/<provider_id>/location"
)
@login_required
def provider_location(
    provider_id
):

    rows = db_select(
        "driver_locations",
        filters={
            "driver_id":
                provider_id
        },
        order="created_at.desc",
        limit=1,
    )

    if not rows:

        return jsonify({
            "ok": False,
            "message":
                "This provider has not shared a GPS location.",
        })

    location = rows[0]

    return jsonify({
        "ok": True,
        "latitude":
            location.get(
                "latitude"
            ),
        "longitude":
            location.get(
                "longitude"
            ),
        "accuracy":
            location.get(
                "accuracy"
            ),
        "updated_at":
            location.get(
                "created_at"
            ),
    })


# ============================================================
# UNIVERSITIES
# ============================================================

@app.route("/universities")
@login_required
def universities():

    universities = db_select(
        "universities",
        order="name.asc",
        limit=200,
    )

    return render_page(
        "Universities",
        r"""
        <div class="card">

            <h2>
                University Applications
            </h2>

            <p>
                Select a university,
                programme and academic year.
            </p>

        </div>

        {% for university in universities %}

            <div class="card">

                <h3>
                    {{ university.get("name")
                       or
                       university.get(
                           "university_name"
                       )
                       or "University" }}
                </h3>

                <p>
                    {{ university.get(
                        "location"
                    )
                    or
                    university.get(
                        "description"
                    )
                    or "" }}
                </p>

                {% if university.get("id") %}

                    <a
                        class="btn"
                        href="{{
                            url_for(
                                'university_apply',
                                university_id=
                                    university.get(
                                        'id'
                                    )
                            )
                        }}"
                    >
                        Apply
                    </a>

                {% endif %}

            </div>

        {% else %}

            <div class="card">

                <p>
                    No universities are currently
                    loaded.
                </p>

            </div>

        {% endfor %}
        """,
        universities=universities,
    )


@app.route(
    "/university/apply/<university_id>",
    methods=["GET", "POST"],
)
@login_required
def university_apply(
    university_id
):

    user = current_user()

    university = first_row(
        "universities",
        {
            "id":
                university_id
        },
    )

    if not university:
        abort(404)

    programmes = db_select(
        "university_programmes",
        filters={
            "university_id":
                university_id
        },
        order="name.asc",
        limit=500,
    )

    requirements = db_select(
        "university_application_requirements",
        filters={
            "university_id":
                university_id
        },
        limit=500,
    )

    if request.method == "POST":

        programme_id = request.form.get(
            "programme_id"
        )

        year = request.form.get(
            "academic_year"
        )

        intake = clean(
            request.form.get(
                "intake"
            )
        )

        payload = {
            "id":
                str(uuid.uuid4()),

            "user_id":
                user["id"],

            "university_id":
                university_id,

            "programme_id":
                programme_id,

            "academic_year":
                year,

            "intake":
                intake or None,

            "full_name":
                user["name"],

            "email":
                user["email"],

            "phone":
                user.get("phone"),

            "status":
                "draft",

            "created_at":
                utc_now(),
        }

        row, error = db_insert(
            "university_applications",
            payload,
        )

        if error:

            minimal = {
                "id":
                    payload["id"],

                "user_id":
                    user["id"],

                "university_id":
                    university_id,

                "programme_id":
                    programme_id,

                "academic_year":
                    year,
            }

            row, error = db_insert(
                "university_applications",
                minimal,
            )

        if error:

            flash(
                "Application could not be created: "
                + str(error)[:700],
                "danger",
            )

        else:

            flash(
                "University application started successfully.",
                "success",
            )

        return redirect(
            url_for("universities")
        )

    return render_page(
        "University Application",
        r"""
        <div class="card">

            <h2>
                {{ university.get("name")
                   or
                   university.get(
                       "university_name"
                   )
                   or "University" }}
            </h2>

            <form method="POST">

                <label>
                    Programme
                </label>

                <select name="programme_id">

                    <option value="">
                        Select programme
                    </option>

                    {% for p in programmes %}

                        <option
                            value="{{ p.get('id') }}"
                        >
                            {{
                                p.get("name")
                                or
                                p.get(
                                    "programme_name"
                                )
                                or
                                p.get(
                                    "title"
                                )
                            }}
                        </option>

                    {% endfor %}

                </select>

                <label>
                    Academic Year
                </label>

                <select name="academic_year">

                    <option value="2026/2027">
                        2026/2027
                    </option>

                    <option value="2027/2028">
                        2027/2028
                    </option>

                    <option value="2028/2029">
                        2028/2029
                    </option>

                </select>

                <label>
                    Intake
                </label>

                <select name="intake">

                    <option value="">
                        Select
                    </option>

                    <option value="January">
                        January
                    </option>

                    <option value="May">
                        May
                    </option>

                    <option value="September">
                        September
                    </option>

                    <option value="Other">
                        Other
                    </option>

                </select>

                <button type="submit">
                    Start Application
                </button>

            </form>

        </div>

        <div class="card">

            <h3>
                Application Requirements
            </h3>

            {% for r in requirements %}

                <div class="card">

                    <strong>
                        {{
                            r.get("title")
                            or
                            r.get("requirement")
                            or "Requirement"
                        }}
                    </strong>

                    <p>
                        {{
                            r.get("description")
                            or
                            r.get("details")
                            or ""
                        }}
                    </p>

                </div>

            {% else %}

                <p>
                    No specific requirements
                    have been entered.
                </p>

            {% endfor %}

        </div>
        """,
        university=university,
        programmes=programmes,
        requirements=requirements,
    )


# ============================================================
# ADMIN DASHBOARD
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
                limit=1000,
            )
        )

    return render_page(
        "Admin Dashboard",
        r"""
        <div class="card">

            <h2>
                KOJA Administrator
            </h2>

            <p>
                System management dashboard.
            </p>

        </div>

        <div class="grid">

            {% for name, count in counts.items() %}

                <div class="card stat">

                    <strong>
                        {{ count }}
                    </strong>

                    {{ name }}

                </div>

            {% endfor %}

        </div>

        <div class="card">

            <h3>
                Management
            </h3>

            <a
                class="btn"
                href="{{ url_for('admin_users') }}"
            >
                Users
            </a>

            <a
                class="btn"
                href="{{ url_for('admin_drivers') }}"
            >
                Drivers
            </a>

            <a
                class="btn"
                href="{{ url_for('admin_deliveries') }}"
            >
                Deliveries
            </a>

            <a
                class="btn"
                href="{{ url_for('admin_appointments') }}"
            >
                Appointments
            </a>

        </div>
        """,
        counts=counts,
    )


# ============================================================
# ADMIN USERS
# ============================================================

@app.route("/admin/users")
@admin_required
def admin_users():

    rows = db_select(
        "profiles",
        order="created_at.desc",
        limit=300,
    )

    return render_page(
        "Admin Users",
        r"""
        <div class="card">

            <h2>
                Users
            </h2>

            {% for u in rows %}

                <div class="card">

                    <strong>
                        {{
                            u.get("full_name")
                            or
                            u.get("name")
                            or ""
                        }}
                    </strong>

                    <p>
                        Email:
                        {{ u.get("email") }}
                    </p>

                    <p>
                        Phone:
                        {{ u.get("phone") or "" }}
                    </p>

                    <p>
                        Role:
                        {{ u.get("role") or "" }}
                    </p>

                    <p>
                        Admin:
                        {{
                            "Yes"
                            if u.get("is_admin")
                            else "No"
                        }}
                    </p>

                </div>

            {% endfor %}

        </div>
        """,
        rows=rows,
    )


# ============================================================
# ADMIN DRIVERS
# ============================================================

@app.route("/admin/drivers")
@admin_required
def admin_drivers():

    rows = db_select(
        "driver_profiles",
        order="created_at.desc",
        limit=300,
    )

    return render_page(
        "Admin Drivers",
        r"""
        <div class="card">

            <h2>
                Drivers
            </h2>

            {% for d in rows %}

                <div class="card">

                    <h3>
                        Driver
                    </h3>

                    <p>
                        Provider ID:
                        {{ d.get("provider_id") }}
                    </p>

                    <p>
                        Vehicle:
                        {{ d.get("vehicle_type") }}
                    </p>

                    <p>
                        Registration:
                        {{ d.get(
                            "vehicle_registration"
                        ) }}
                    </p>

                    <p>
                        Licence:
                        {{ d.get(
                            "driving_license_number"
                        ) }}
                    </p>

                    <p>
                        Verification:
                        {{
                            d.get(
                                "verification_status"
                            )
                            or "pending"
                        }}
                    </p>

                </div>

            {% endfor %}

        </div>
        """,
        rows=rows,
    )


# ============================================================
# ADMIN DELIVERIES
# ============================================================

@app.route("/admin/deliveries")
@admin_required
def admin_deliveries():

    rows = db_select(
        "deliveries",
        order="created_at.desc",
        limit=300,
    )

    return render_page(
        "Admin Deliveries",
        r"""
        <div class="card">

            <h2>
                Deliveries
            </h2>

            {% for d in rows %}

                <div class="card">

                    <strong>
                        {{ d.get(
                            "tracking_code"
                        ) }}
                    </strong>

                    <p>
                        Customer:
                        {{ d.get(
                            "customer_id"
                        ) }}
                    </p>

                    <p>
                        Pickup:
                        {{ d.get(
                            "pickup_location"
                        ) }}
                    </p>

                    <p>
                        Destination:
                        {{ d.get(
                            "destination"
                        ) }}
                    </p>

                    <p>
                        Driver:
                        {{
                            d.get("driver_id")
                            or "Unassigned"
                        }}
                    </p>

                    <p>
                        Status:
                        {{ d.get("status") }}
                    </p>

                </div>

            {% endfor %}

        </div>
        """,
        rows=rows,
    )


# ============================================================
# ADMIN APPOINTMENTS
# ============================================================

@app.route("/admin/appointments")
@admin_required
def admin_appointments():

    rows = db_select(
        "appointments",
        order="created_at.desc",
        limit=300,
    )

    return render_page(
        "Admin Appointments",
        r"""
        <div class="card">

            <h2>
                Appointments
            </h2>

            {% for a in rows %}

                <div class="card">

                    <p>
                        Date:
                        {{ a.get(
                            "appointment_date"
                        ) }}
                    </p>

                    <p>
                        Client:
                        {{ a.get(
                            "client_id"
                        ) }}
                    </p>

                    <p>
                        Provider:
                        {{ a.get(
                            "provider_id"
                        ) }}
                    </p>

                    <p>
                        Type:
                        {{ a.get(
                            "appointment_type"
                        ) }}
                    </p>

                    <p>
                        Status:
                        {{ a.get("status") }}
                    </p>

                </div>

            {% endfor %}

        </div>
        """,
        rows=rows,
    )


# ============================================================
# ERROR HANDLERS
# ============================================================

@app.errorhandler(404)
def not_found(error):

    return render_page(
        "Not Found",
        r"""
        <div class="card">

            <h2>
                Page Not Found
            </h2>

            <p>
                The requested page does not exist.
            </p>

            <a
                class="btn"
                href="{{ url_for('home') }}"
            >
                Return Home
            </a>

        </div>
        """,
    ), 404


@app.errorhandler(413)
def too_large(error):

    return render_page(
        "File Too Large",
        r"""
        <div class="card">

            <h2>
                File Too Large
            </h2>

            <p>
                The maximum upload size is
                {{ max_mb }} MB.
            </p>

        </div>
        """,
        max_mb=MAX_UPLOAD_MB,
    ), 413


@app.errorhandler(500)
def internal_error(error):

    logger.exception(
        "Unhandled application error"
    )

    return render_page(
        "Server Error",
        r"""
        <div class="card">

            <h2>
                KOJA AFRICA Server Error
            </h2>

            <p>
                The server encountered an
                unexpected error.
            </p>

            <p>
                Check Render logs for details.
            </p>

            <a
                class="btn"
                href="{{ url_for('home') }}"
            >
                Return Home
            </a>

        </div>
        """,
    ), 500


# ============================================================
# GLOBAL CONTEXT
# ============================================================

@app.context_processor
def inject_globals():

    return {
        "APP_NAME":
            APP_NAME,

        "APP_TAGLINE":
            APP_TAGLINE,
    }


# ============================================================
# STARTUP
# ============================================================

if __name__ == "__main__":

    port = int(
        os.getenv(
            "PORT",
            "5000",
        )
    )

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False,
    )

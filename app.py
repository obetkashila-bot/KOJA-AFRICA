import os
import io
import uuid
import json
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
    abort,
)

from werkzeug.security import generate_password_hash

load_dotenv()

# ============================================================
# KOJA AFRICA
# Knowledge • Questions • Answers
#
# Flask + Supabase REST API
# Compatible with existing KOJA database
# ============================================================

app = Flask(__name__)

app.secret_key = os.getenv(
    "FLASK_SECRET_KEY",
    os.getenv("SECRET_KEY", "change-this-secret-key")
)

app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024


# ============================================================
# CONFIGURATION
# ============================================================

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")

# Some deployments use SUPABASE_ANON_KEY.
# Service key is preferred for server-side REST operations.
if not SUPABASE_KEY:
    SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY", "")

SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")

FLW_SECRET_KEY = os.getenv("FLW_SECRET_KEY", "")
FLW_SECRET_HASH = os.getenv("FLW_SECRET_HASH", "")

PAYMENT_CURRENCY = os.getenv("PAYMENT_CURRENCY", "ZMW")
DEFAULT_ANSWER_PRICE = os.getenv("KOJA_PAYMENT_AMOUNT", "10.00")

STORAGE_BUCKET = os.getenv("KOJA_STORAGE_BUCKET", "koja-files")

ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "").strip().lower()
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")

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


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("koja")


# ============================================================
# VALIDATION
# ============================================================

def configuration_error():
    missing = []

    if not SUPABASE_URL:
        missing.append("SUPABASE_URL")

    if not SUPABASE_KEY:
        missing.append("SUPABASE_SERVICE_KEY or SUPABASE_ANON_KEY")

    if missing:
        return "Missing environment variables: " + ", ".join(missing)

    return None


def valid_email(email):
    if not email:
        return False

    email = email.strip()

    if "@" not in email:
        return False

    if "." not in email.split("@")[-1]:
        return False

    return True


def valid_password(password):
    return bool(password and len(password) >= 6)


def allowed_file(filename):
    if not filename:
        return False

    if "." not in filename:
        return False

    ext = filename.rsplit(".", 1)[1].lower()

    return ext in ALLOWED_EXTENSIONS


def clean(value):
    if value is None:
        return ""

    return str(value).strip()


# ============================================================
# SUPABASE HEADERS
# ============================================================

def supabase_headers(prefer=None):
    key = SUPABASE_KEY

    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }

    if prefer:
        headers["Prefer"] = prefer

    return headers


def service_headers(prefer=None):
    key = SUPABASE_SERVICE_KEY or SUPABASE_KEY

    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }

    if prefer:
        headers["Prefer"] = prefer

    return headers


# ============================================================
# SUPABASE REST
# ============================================================

def rest_url(table):
    return f"{SUPABASE_URL}/rest/v1/{table}"


def rest_select(
    table,
    params=None,
    use_service=True,
):
    try:
        headers = service_headers()

        response = requests.get(
            rest_url(table),
            headers=headers,
            params=params or {},
            timeout=30,
        )

        if response.status_code >= 400:
            logger.error(
                "SELECT %s failed: %s",
                table,
                response.text
            )
            return None

        return response.json()

    except Exception:
        logger.exception("Supabase SELECT error")
        return None


def rest_insert(
    table,
    data,
    select="*",
):
    try:
        headers = service_headers(
            f"return=representation"
        )

        response = requests.post(
            rest_url(table),
            headers=headers,
            params={"select": select},
            json=data,
            timeout=30,
        )

        if response.status_code >= 400:
            logger.error(
                "INSERT %s failed: %s",
                table,
                response.text
            )
            return None

        return response.json()

    except Exception:
        logger.exception("Supabase INSERT error")
        return None


def rest_update(
    table,
    filters,
    data,
):
    try:
        headers = service_headers(
            "return=representation"
        )

        response = requests.patch(
            rest_url(table),
            headers=headers,
            params=filters,
            json=data,
            timeout=30,
        )

        if response.status_code >= 400:
            logger.error(
                "UPDATE %s failed: %s",
                table,
                response.text
            )
            return None

        return response.json()

    except Exception:
        logger.exception("Supabase UPDATE error")
        return None


def rest_delete(
    table,
    filters,
):
    try:
        headers = service_headers()

        response = requests.delete(
            rest_url(table),
            headers=headers,
            params=filters,
            timeout=30,
        )

        if response.status_code >= 400:
            logger.error(
                "DELETE %s failed: %s",
                table,
                response.text
            )
            return False

        return True

    except Exception:
        logger.exception("Supabase DELETE error")
        return False


# ============================================================
# SUPABASE AUTH
# ============================================================

def auth_signup(email, password):
    try:
        response = requests.post(
            f"{SUPABASE_URL}/auth/v1/signup",
            headers={
                "apikey": SUPABASE_KEY,
                "Content-Type": "application/json",
            },
            json={
                "email": email,
                "password": password,
            },
            timeout=30,
        )

        try:
            data = response.json()
        except Exception:
            data = {}

        if response.status_code >= 400:
            return False, data.get(
                "msg",
                data.get(
                    "message",
                    data.get(
                        "error_description",
                        "Registration failed."
                    )
                )
            ), data

        return True, "Registration successful.", data

    except Exception as exc:
        logger.exception("Auth signup failed")
        return False, str(exc), {}


def auth_login(email, password):
    try:
        response = requests.post(
            f"{SUPABASE_URL}/auth/v1/token",
            params={"grant_type": "password"},
            headers={
                "apikey": SUPABASE_KEY,
                "Content-Type": "application/json",
            },
            json={
                "email": email,
                "password": password,
            },
            timeout=30,
        )

        try:
            data = response.json()
        except Exception:
            data = {}

        if response.status_code >= 400:
            message = data.get(
                "msg",
                data.get(
                    "message",
                    data.get(
                        "error_description",
                        "Invalid email or password."
                    )
                )
            )

            return False, message, data

        return True, "Login successful.", data

    except Exception as exc:
        logger.exception("Auth login failed")
        return False, str(exc), {}


def auth_user(access_token):
    if not access_token:
        return None

    try:
        response = requests.get(
            f"{SUPABASE_URL}/auth/v1/user",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {access_token}",
            },
            timeout=30,
        )

        if response.status_code >= 400:
            return None

        return response.json()

    except Exception:
        return None


# ============================================================
# SESSION
# ============================================================

def current_user():
    return session.get("user")


def current_user_id():
    user = current_user()

    if not user:
        return None

    return user.get("id")


def current_email():
    user = current_user()

    if not user:
        return ""

    return (
        user.get("email")
        or session.get("email")
        or ""
    ).lower()


def is_admin():
    email = current_email()

    if not email:
        return False

    if ADMIN_EMAIL and email == ADMIN_EMAIL:
        return True

    user = current_user() or {}

    app_metadata = user.get("app_metadata") or {}
    user_metadata = user.get("user_metadata") or {}

    role = (
        app_metadata.get("role")
        or user_metadata.get("role")
        or session.get("role")
    )

    return str(role).lower() == "admin"


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):

        if not current_user_id():
            flash("Please login first.", "warning")
            return redirect(url_for("login"))

        return view(*args, **kwargs)

    return wrapper


def admin_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):

        if not current_user_id():
            flash("Please login first.", "warning")
            return redirect(url_for("login"))

        if not is_admin():
            flash("Administrator access required.", "danger")
            return redirect(url_for("dashboard"))

        return view(*args, **kwargs)

    return wrapper


# ============================================================
# GENERIC TABLE HELPERS
# ============================================================

def first_row(table, filters):
    rows = rest_select(
        table,
        params={
            **filters,
            "limit": "1",
        },
    )

    if rows:
        return rows[0]

    return None


def table_exists(table):
    """
    REST does not expose information_schema through /rest/v1.
    We therefore test the table endpoint.
    """

    try:
        response = requests.get(
            rest_url(table),
            headers=service_headers(),
            params={"limit": "1"},
            timeout=15,
        )

        return response.status_code < 400

    except Exception:
        return False


def insert_if_possible(table, data):
    """
    Insert into a legacy-compatible table.

    If a table rejects unknown columns, progressively remove
    optional columns and retry.
    """

    result = rest_insert(table, data)

    if result is not None:
        return result

    # Common columns that may not exist in old KOJA tables.
    optional = [
        "updated_at",
        "created_at",
        "admin_notes",
        "status",
        "service_request_id",
        "user_id",
        "description",
        "priority",
        "amount",
        "currency",
    ]

    reduced = dict(data)

    for column in optional:

        if column not in reduced:
            continue

        reduced.pop(column, None)

        result = rest_insert(table, reduced)

        if result is not None:
            return result

    return None


# ============================================================
# PROFILE COMPATIBILITY
# ============================================================

def create_compatible_profile(user, name="", phone=""):
    """
    KOJA has several profile/user tables from older versions.

    We try profiles first and only send columns that are common
    across versions.
    """

    uid = user.get("id")
    email = user.get("email", "")

    candidates = [
        "profiles",
        "koja_users",
        "koja_clients",
    ]

    for table in candidates:

        if not table_exists(table):
            continue

        data = {
            "id": uid,
            "user_id": uid,
            "email": email,
            "full_name": name,
            "name": name,
            "phone": phone,
            "role": "student",
            "user_type": "student",
        }

        # Try different compatibility payloads.
        attempts = [
            data,
            {
                "id": uid,
                "email": email,
                "full_name": name,
                "phone": phone,
                "role": "student",
            },
            {
                "id": uid,
                "email": email,
                "name": name,
            },
            {
                "user_id": uid,
                "email": email,
                "name": name,
            },
        ]

        for payload in attempts:

            result = rest_insert(
                table,
                payload,
            )

            if result is not None:
                logger.info(
                    "Profile created in %s",
                    table
                )
                return result

    return None


# ============================================================
# ACTIVITY LOG
# ============================================================

def log_activity(
    action,
    description="",
    service_request_id=None,
    old_status=None,
    new_status=None,
):
    try:

        payload = {
            "user_id": current_user_id(),
            "email": current_email(),
            "action": action,
            "description": description,
            "service_request_id": service_request_id,
            "old_status": old_status,
            "new_status": new_status,
            "ip_address": request.remote_addr,
            "user_agent": request.headers.get(
                "User-Agent",
                ""
            ),
        }

        # Remove None values
        payload = {
            k: v
            for k, v in payload.items()
            if v is not None
        }

        rest_insert(
            "activity_logs",
            payload
        )

    except Exception:
        logger.exception("Activity log failed")


# ============================================================
# STORAGE
# ============================================================

def upload_storage(
    filename,
    file_bytes,
    content_type="application/octet-stream",
):
    """
    Upload to Supabase Storage.

    Returns storage path or None.
    """

    safe_name = (
        filename
        .replace("/", "_")
        .replace("\\", "_")
    )

    storage_path = (
        f"uploads/{uuid.uuid4()}_{safe_name}"
    )

    try:

        url = (
            f"{SUPABASE_URL}/storage/v1/object/"
            f"{STORAGE_BUCKET}/{storage_path}"
        )

        response = requests.post(
            url,
            headers={
                "Authorization":
                    f"Bearer {SUPABASE_SERVICE_KEY or SUPABASE_KEY}",
                "apikey":
                    SUPABASE_SERVICE_KEY or SUPABASE_KEY,
                "Content-Type":
                    content_type,
            },
            data=file_bytes,
            timeout=60,
        )

        if response.status_code >= 400:
            logger.error(
                "Storage upload failed: %s",
                response.text
            )
            return None

        return storage_path

    except Exception:
        logger.exception("Storage error")
        return None


def storage_download(path):
    try:

        url = (
            f"{SUPABASE_URL}/storage/v1/object/"
            f"{STORAGE_BUCKET}/{path}"
        )

        response = requests.get(
            url,
            headers={
                "Authorization":
                    f"Bearer {SUPABASE_SERVICE_KEY or SUPABASE_KEY}",
                "apikey":
                    SUPABASE_SERVICE_KEY or SUPABASE_KEY,
            },
            timeout=60,
        )

        if response.status_code >= 400:
            return None, None

        return (
            response.content,
            response.headers.get(
                "Content-Type",
                "application/octet-stream"
            ),
        )

    except Exception:
        logger.exception("Storage download failed")
        return None, None


# ============================================================
# HTML
# ============================================================

BASE_HTML = """
<!doctype html>
<html lang="en">
<head>

<meta charset="utf-8">
<meta name="viewport"
      content="width=device-width, initial-scale=1">

<title>{{ title or "KOJA Africa" }}</title>

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
    background: #f4f7fb;
    color: #172033;
}

nav {
    background: #101c36;
    color: white;
    padding: 14px 18px;
    position: sticky;
    top: 0;
    z-index: 10;
}

.nav-inner {
    max-width: 1100px;
    margin: auto;
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 10px;
}

.logo {
    font-size: 21px;
    font-weight: 800;
}

.logo span {
    color: #52d273;
}

.nav-links {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
}

.nav-links a {
    color: white;
    text-decoration: none;
    padding: 8px 10px;
    border-radius: 7px;
}

.nav-links a:hover {
    background: rgba(255,255,255,.12);
}

.container {
    max-width: 1100px;
    margin: 25px auto;
    padding: 0 15px;
}

.hero {
    background: linear-gradient(
        135deg,
        #101c36,
        #173c67
    );
    color: white;
    border-radius: 16px;
    padding: 35px 25px;
    margin-bottom: 22px;
}

.hero h1 {
    margin-top: 0;
    font-size: 32px;
}

.hero p {
    color: #dce8f7;
    line-height: 1.6;
}

.grid {
    display: grid;
    grid-template-columns:
        repeat(auto-fit, minmax(220px, 1fr));
    gap: 15px;
}

.card {
    background: white;
    border-radius: 13px;
    padding: 20px;
    box-shadow:
        0 4px 18px rgba(0,0,0,.06);
    margin-bottom: 15px;
}

.card h3 {
    margin-top: 0;
}

.btn {
    display: inline-block;
    border: 0;
    border-radius: 8px;
    padding: 11px 16px;
    text-decoration: none;
    cursor: pointer;
    background: #173c67;
    color: white;
    font-weight: 700;
}

.btn.green {
    background: #17863a;
}

.btn.red {
    background: #bd2735;
}

.btn.gray {
    background: #697386;
}

.btn.small {
    padding: 7px 10px;
    font-size: 13px;
}

form {
    background: white;
    padding: 22px;
    border-radius: 13px;
    box-shadow:
        0 4px 18px rgba(0,0,0,.06);
}

label {
    display: block;
    font-weight: 700;
    margin-top: 13px;
    margin-bottom: 6px;
}

input,
textarea,
select {
    width: 100%;
    padding: 12px;
    border: 1px solid #ccd4df;
    border-radius: 8px;
    font-size: 15px;
}

textarea {
    min-height: 130px;
    resize: vertical;
}

button {
    margin-top: 18px;
}

.alert {
    padding: 12px 15px;
    margin-bottom: 14px;
    border-radius: 8px;
    background: #e9f2ff;
}

.alert.danger {
    background: #ffe8eb;
    color: #8b1723;
}

.alert.success {
    background: #e8f8ec;
    color: #176b2f;
}

.alert.warning {
    background: #fff6db;
    color: #765700;
}

table {
    width: 100%;
    border-collapse: collapse;
}

th,
td {
    padding: 10px;
    border-bottom: 1px solid #e5e9ef;
    text-align: left;
}

.badge {
    display: inline-block;
    padding: 5px 9px;
    border-radius: 999px;
    background: #e9edf5;
    font-size: 12px;
}

footer {
    margin-top: 50px;
    padding: 30px;
    text-align: center;
    background: #101c36;
    color: white;
}

@media(max-width:600px) {

    .nav-inner {
        align-items: flex-start;
        flex-direction: column;
    }

    .hero h1 {
        font-size: 25px;
    }

    th,
    td {
        font-size: 13px;
    }
}

</style>
</head>

<body>

<nav>
<div class="nav-inner">

<div class="logo">
KOJA <span>AFRICA</span>
</div>

<div class="nav-links">

<a href="{{ url_for('home') }}">Home</a>

{% if session.get("user") %}
<a href="{{ url_for('dashboard') }}">Dashboard</a>
<a href="{{ url_for('services') }}">Services</a>
<a href="{{ url_for('documents') }}">Resources</a>

{% if admin %}
<a href="{{ url_for('admin_dashboard') }}">Admin</a>
{% endif %}

<a href="{{ url_for('logout') }}">Logout</a>

{% else %}

<a href="{{ url_for('login') }}">Login</a>
<a href="{{ url_for('register') }}">Register</a>

{% endif %}

</div>

</div>
</nav>

<div class="container">

{% with messages = get_flashed_messages(with_categories=true) %}

{% for category, message in messages %}

<div class="alert {{ category }}">
{{ message }}
</div>

{% endfor %}

{% endwith %}

{{ body|safe }}

</div>

<footer>
KOJA AFRICA<br>
Knowledge • Questions • Answers
</footer>

</body>
</html>
"""


def page(title, body):
    return render_template_string(
        BASE_HTML,
        title=title,
        body=body,
        admin=is_admin(),
    )


# ============================================================
# HOME
# ============================================================

@app.route("/")
def home():

    return page(
        "KOJA Africa",
        """
        <section class="hero">

        <h1>KOJA AFRICA</h1>

        <p>
        Knowledge • Questions • Answers
        </p>

        <p>
        Academic assistance, assignments, CV services,
        farmer registration assistance, TPIN assistance,
        doctor booking, lawyer booking, tutoring,
        delivery and other digital services.
        </p>

        <a class="btn green"
           href="/register">
           Create Account
        </a>

        <a class="btn"
           href="/services">
           Explore Services
        </a>

        </section>

        <div class="grid">

        <div class="card">
        <h3>🎓 Academic</h3>
        <p>
        Academic questions, learning materials and
        assignment support.
        </p>
        </div>

        <div class="card">
        <h3>📄 CV & Career</h3>
        <p>
        Professional CV and career document preparation.
        </p>
        </div>

        <div class="card">
        <h3>🌾 Farmer Services</h3>
        <p>
        Assistance with farmer registration and related
        services.
        </p>
        </div>

        <div class="card">
        <h3>🧾 TPIN</h3>
        <p>
        TPIN assistance for individuals and businesses.
        </p>
        </div>

        <div class="card">
        <h3>🏥 Doctor Booking</h3>
        <p>
        Request healthcare appointment assistance.
        </p>
        </div>

        <div class="card">
        <h3>⚖️ Lawyer Booking</h3>
        <p>
        Request legal consultation assistance.
        </p>
        </div>

        <div class="card">
        <h3>👨‍🏫 Teachers & Tutors</h3>
        <p>
        Connect with teachers and tutors.
        </p>
        </div>

        <div class="card">
        <h3>🚚 Delivery</h3>
        <p>
        Request driver and delivery services.
        </p>
        </div>

        </div>
        """
    )


# ============================================================
# REGISTER
# ============================================================

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        name = clean(
            request.form.get("name")
        )

        phone = clean(
            request.form.get("phone")
        )

        email = clean(
            request.form.get("email")
        ).lower()

        password = request.form.get(
            "password",
            ""
        )

        confirm = request.form.get(
            "confirm_password",
            ""
        )

        if not name:
            flash(
                "Please enter your full name.",
                "danger"
            )
            return redirect(
                url_for("register")
            )

        if not valid_email(email):
            flash(
                "Please enter a valid email address.",
                "danger"
            )
            return redirect(
                url_for("register")
            )

        if not valid_password(password):
            flash(
                "Password must contain at least 6 characters.",
                "danger"
            )
            return redirect(
                url_for("register")
            )

        if password != confirm:
            flash(
                "Passwords do not match.",
                "danger"
            )
            return redirect(
                url_for("register")
            )

        success, message, data = auth_signup(
            email,
            password
        )

        if not success:

            logger.error(
                "Registration error: %s",
                message
            )

            flash(
                message,
                "danger"
            )

            return redirect(
                url_for("register")
            )

        # Supabase can return a user immediately
        # or require email confirmation.
        user = data.get("user")

        if user:
            create_compatible_profile(
                user,
                name=name,
                phone=phone
            )

        flash(
            "Account created successfully. "
            "If email confirmation is enabled in Supabase, "
            "check your email before logging in.",
            "success"
        )

        return redirect(
            url_for("login")
        )

    return page(
        "Create Account",
        """
        <div class="card">

        <h2>Create your KOJA Africa account</h2>

        <form method="POST">

        <label>Full name</label>
        <input
            type="text"
            name="name"
            required
            autocomplete="name">

        <label>Phone number</label>
        <input
            type="tel"
            name="phone"
            placeholder="097XXXXXXX">

        <label>Email address</label>
        <input
            type="email"
            name="email"
            required
            autocomplete="email">

        <label>Password</label>
        <input
            type="password"
            name="password"
            required
            minlength="6"
            autocomplete="new-password">

        <label>Confirm password</label>
        <input
            type="password"
            name="confirm_password"
            required
            minlength="6"
            autocomplete="new-password">

        <button class="btn green"
                type="submit">
            Create Account
        </button>

        </form>

        <p>
        Already have an account?
        <a href="/login">Login</a>
        </p>

        </div>
        """
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

        if not valid_email(email):
            flash(
                "Please enter a valid email address.",
                "danger"
            )
            return redirect(
                url_for("login")
            )

        success, message, data = auth_login(
            email,
            password
        )

        if not success:

            # Make Supabase's actual error useful.
            if "Email not confirmed" in message:
                message = (
                    "Your email has not been confirmed. "
                    "Check your email or disable email "
                    "confirmation in Supabase Authentication "
                    "for testing."
                )

            flash(
                message,
                "danger"
            )

            return redirect(
                url_for("login")
            )

        access_token = data.get(
            "access_token"
        )

        refresh_token = data.get(
            "refresh_token"
        )

        user = data.get("user")

        if not user and access_token:
            user = auth_user(
                access_token
            )

        if not user:
            flash(
                "Login succeeded but user information "
                "could not be loaded.",
                "danger"
            )
            return redirect(
                url_for("login")
            )

        session.clear()

        session["access_token"] = access_token
        session["refresh_token"] = refresh_token
        session["user"] = user
        session["email"] = (
            user.get("email", email)
        )

        # Determine admin from environment first.
        if ADMIN_EMAIL and email == ADMIN_EMAIL:
            session["role"] = "admin"

        log_activity(
            "login",
            "User logged into KOJA Africa."
        )

        flash(
            "Welcome to KOJA Africa.",
            "success"
        )

        return redirect(
            url_for("dashboard")
        )

    return page(
        "Login",
        """
        <div class="card">

        <h2>Login</h2>

        <form method="POST">

        <label>Email address</label>

        <input
            type="email"
            name="email"
            required
            autocomplete="email">

        <label>Password</label>

        <input
            type="password"
            name="password"
            required
            autocomplete="current-password">

        <button class="btn green"
                type="submit">
            Login
        </button>

        </form>

        <p>
        No account?
        <a href="/register">Create one</a>
        </p>

        </div>
        """
    )


# ============================================================
# LOGOUT
# ============================================================

@app.route("/logout")
def logout():

    log_activity(
        "logout",
        "User logged out."
    )

    session.clear()

    flash(
        "You have been logged out.",
        "success"
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

    uid = current_user_id()

    assignments = rest_select(
        "assignment_requests",
        {
            "user_id": f"eq.{uid}",
            "order": "created_at.desc",
            "limit": "10",
        }
    ) or []

    service_requests = rest_select(
        "service_requests",
        {
            "user_id": f"eq.{uid}",
            "order": "created_at.desc",
            "limit": "10",
        }
    ) or []

    notifications = rest_select(
        "notifications",
        {
            "user_id": f"eq.{uid}",
            "order": "created_at.desc",
            "limit": "10",
        }
    ) or []

    # Some KOJA versions use koja_notifications.
    if not notifications:
        notifications = rest_select(
            "koja_notifications",
            {
                "user_id": f"eq.{uid}",
                "order": "created_at.desc",
                "limit": "10",
            }
        ) or []

    rows = ""

    for item in service_requests:

        rows += f"""
        <tr>
        <td>{clean(item.get('title'))}</td>
        <td>
        <span class="badge">
        {clean(item.get('status'))}
        </span>
        </td>
        <td>
        {clean(item.get('created_at'))}
        </td>
        </tr>
        """

    if not rows:
        rows = """
        <tr>
        <td colspan="3">
        No service requests yet.
        </td>
        </tr>
        """

    return page(
        "Dashboard",
        f"""
        <section class="hero">

        <h1>Welcome to KOJA Africa</h1>

        <p>
        {clean(current_email())}
        </p>

        </section>

        <div class="grid">

        <div class="card">
        <h3>🎓 Academic</h3>
        <a class="btn"
           href="/service/academic">
           Request Academic Help
        </a>
        </div>

        <div class="card">
        <h3>📝 Assignment</h3>
        <a class="btn"
           href="/assignment/new">
           Submit Assignment
        </a>
        </div>

        <div class="card">
        <h3>📄 CV</h3>
        <a class="btn"
           href="/cv/new">
           Create CV
        </a>
        </div>

        <div class="card">
        <h3>🌾 Farmer</h3>
        <a class="btn"
           href="/farmer/new">
           Farmer Registration
        </a>
        </div>

        <div class="card">
        <h3>🧾 TPIN</h3>
        <a class="btn"
           href="/tpin/new">
           TPIN Assistance
        </a>
        </div>

        <div class="card">
        <h3>🏥 Doctor</h3>
        <a class="btn"
           href="/doctor/new">
           Doctor Booking
        </a>
        </div>

        <div class="card">
        <h3>⚖️ Lawyer</h3>
        <a class="btn"
           href="/lawyer/new">
           Lawyer Booking
        </a>
        </div>

        <div class="card">
        <h3>🚚 Delivery</h3>
        <a class="btn"
           href="/delivery/new">
           Request Delivery
        </a>
        </div>

        </div>

        <div class="card">

        <h2>My Service Requests</h2>

        <table>

        <tr>
        <th>Service</th>
        <th>Status</th>
        <th>Date</th>
        </tr>

        {rows}

        </table>

        </div>

        <div class="card">

        <h2>Notifications</h2>

        <p>
        {len(notifications)}
        notification(s)
        </p>

        </div>

        <div class="card">

        <h2>Assignments</h2>

        <p>
        {len(assignments)}
        assignment request(s)
        </p>

        </div>
        """
    )


# ============================================================
# SERVICES
# ============================================================

@app.route("/services")
def services():

    categories = rest_select(
        "service_categories",
        {
            "is_active": "eq.true",
            "order": "name.asc",
        }
    ) or []

    cards = ""

    for category in categories:

        slug = clean(
            category.get("slug")
        )

        cards += f"""
        <div class="card">

        <h3>
        {clean(category.get('icon'))}
        {clean(category.get('name'))}
        </h3>

        <p>
        {clean(category.get('description'))}
        </p>

        <a class="btn"
           href="/service/{slug}">
           Request Service
        </a>

        </div>
        """

    if not cards:

        cards = """
        <div class="card">
        <p>
        KOJA services are currently being configured.
        </p>
        </div>
        """

    return page(
        "Services",
        f"""
        <h1>KOJA Africa Services</h1>

        <div class="grid">
        {cards}
        </div>
        """
    )


# ============================================================
# GENERIC SERVICE REQUEST
# ============================================================

@app.route(
    "/service/<slug>",
    methods=["GET", "POST"]
)
@login_required
def service_request(slug):

    category = first_row(
        "service_categories",
        {
            "slug": f"eq.{slug}",
        }
    )

    if not category:
        abort(404)

    if request.method == "POST":

        title = clean(
            request.form.get("title")
        )

        description = clean(
            request.form.get("description")
        )

        if not title:
            title = category.get(
                "name",
                "KOJA Service"
            )

        # First create the central request.
        payload = {
            "user_id": current_user_id(),
            "service_category_id":
                category.get("id"),
            "title": title,
            "description": description,
            "status": "submitted",
            "priority": "normal",
            "currency": PAYMENT_CURRENCY,
        }

        result = insert_if_possible(
            "service_requests",
            payload
        )

        if result:

            service_id = result[0].get("id")

            log_activity(
                "service_request_created",
                f"Created {slug} service request.",
                service_request_id=service_id,
            )

            flash(
                "Your service request has been submitted.",
                "success"
            )

            return redirect(
                url_for("dashboard")
            )

        flash(
            "KOJA could not create the service request. "
            "Please check the Supabase logs.",
            "danger"
        )

    return page(
        category.get(
            "name",
            "KOJA Service"
        ),
        f"""
        <div class="card">

        <h2>
        {clean(category.get('icon'))}
        {clean(category.get('name'))}
        </h2>

        <p>
        {clean(category.get('description'))}
        </p>

        <form method="POST">

        <label>Request title</label>

        <input
            type="text"
            name="title"
            placeholder="What do you need?"
            required>

        <label>Describe what you need</label>

        <textarea
            name="description"
            placeholder="Provide all important details..."
            required></textarea>

        <button
            class="btn green"
            type="submit">
            Submit Request
        </button>

        </form>

        </div>
        """
    )


# ============================================================
# ASSIGNMENT
# ============================================================

@app.route(
    "/assignment/new",
    methods=["GET", "POST"]
)
@login_required
def new_assignment():

    if request.method == "POST":

        institution = clean(
            request.form.get("institution")
        )

        programme = clean(
            request.form.get("programme")
        )

        course = clean(
            request.form.get("course")
        )

        subject = clean(
            request.form.get("subject")
        )

        class_level = clean(
            request.form.get("class_level")
        )

        title = clean(
            request.form.get("assignment_title")
        )

        question = clean(
            request.form.get("question")
        )

        requirements = clean(
            request.form.get(
                "lecturer_requirements"
            )
        )

        deadline = clean(
            request.form.get("deadline")
        )

        # Central service request.
        service_payload = {
            "user_id": current_user_id(),
            "title": title or "Assignment Assistance",
            "description": question,
            "status": "submitted",
            "priority": "normal",
            "currency": PAYMENT_CURRENCY,
        }

        service_result = insert_if_possible(
            "service_requests",
            service_payload
        )

        service_id = None

        if service_result:
            service_id = service_result[0].get(
                "id"
            )

        assignment_payload = {
            "user_id": current_user_id(),
            "service_request_id": service_id,
            "institution": institution,
            "programme": programme,
            "course": course,
            "subject": subject,
            "assignment_title": title,
            "deadline": deadline or None,
            "question_text": question,
            "question": question,
            "class_level": class_level,
            "lecturer_requirements": requirements,
            "additional_information": "",
            "status": "submitted",
        }

        result = insert_if_possible(
            "assignment_requests",
            assignment_payload
        )

        if result:

            assignment_id = result[0].get(
                "id"
            )

            log_activity(
                "assignment_submitted",
                "New assignment request submitted.",
                service_request_id=service_id,
            )

            flash(
                "Assignment submitted successfully.",
                "success"
            )

            return redirect(
                url_for("dashboard")
            )

        flash(
            "Assignment could not be submitted.",
            "danger"
        )

    return page(
        "Submit Assignment",
        """
        <div class="card">

        <h2>Submit Assignment</h2>

        <form method="POST">

        <label>Institution</label>
        <input name="institution">

        <label>Programme</label>
        <input name="programme">

        <label>Course</label>
        <input name="course">

        <label>Subject</label>
        <input name="subject">

        <label>Class level</label>
        <input name="class_level">

        <label>Assignment title</label>
        <input
            name="assignment_title"
            required>

        <label>Deadline</label>
        <input
            type="date"
            name="deadline">

        <label>Question / Assignment</label>

        <textarea
            name="question"
            required></textarea>

        <label>
        Lecturer requirements
        </label>

        <textarea
            name="lecturer_requirements">
        </textarea>

        <button
            class="btn green"
            type="submit">
            Submit Assignment
        </button>

        </form>

        </div>
        """
    )


# ============================================================
# CV
# ============================================================

@app.route(
    "/cv/new",
    methods=["GET", "POST"]
)
@login_required
def new_cv():

    if request.method == "POST":

        full_name = clean(
            request.form.get("full_name")
        )

        phone = clean(
            request.form.get("phone")
        )

        email = clean(
            request.form.get("email")
        )

        title = clean(
            request.form.get(
                "professional_title"
            )
        )

        summary = clean(
            request.form.get(
                "professional_summary"
            )
        )

        education = clean(
            request.form.get("education")
        )

        experience = clean(
            request.form.get("experience")
        )

        skills = clean(
            request.form.get("skills")
        )

        certificates = clean(
            request.form.get("certificates")
        )

        target_job = clean(
            request.form.get("target_job")
        )

        service_payload = {
            "user_id": current_user_id(),
            "title": "CV & Career Service",
            "description":
                f"CV for {full_name}",
            "status": "submitted",
            "priority": "normal",
            "currency": PAYMENT_CURRENCY,
        }

        service_result = insert_if_possible(
            "service_requests",
            service_payload
        )

        service_id = None

        if service_result:
            service_id = service_result[0].get(
                "id"
            )

        payload = {
            "user_id": current_user_id(),
            "service_request_id": service_id,
            "full_name": full_name,
            "phone": phone,
            "email": email,
            "professional_title": title,
            "professional_summary": summary,
            "education": (
                json.dumps(
                    [education]
                )
                if education
                else "[]"
            ),
            "experience": (
                json.dumps(
                    [experience]
                )
                if experience
                else "[]"
            ),
            "skills": (
                json.dumps(
                    [skills]
                )
                if skills
                else "[]"
            ),
            "certificates": (
                json.dumps(
                    [certificates]
                )
                if certificates
                else "[]"
            ),
            "references_data": "[]",
            "target_job": target_job,
            "template": "professional",
            "status": "submitted",
        }

        result = insert_if_possible(
            "cv_requests",
            payload
        )

        if result:

            log_activity(
                "cv_request_created",
                "New CV request submitted.",
                service_request_id=service_id,
            )

            flash(
                "CV request submitted successfully.",
                "success"
            )

            return redirect(
                url_for("dashboard")
            )

        flash(
            "CV request could not be submitted.",
            "danger"
        )

    return page(
        "CV Service",
        """
        <div class="card">

        <h2>CV & Career Service</h2>

        <form method="POST">

        <label>Full name</label>
        <input name="full_name" required>

        <label>Phone</label>
        <input name="phone">

        <label>Email</label>
        <input type="email" name="email">

        <label>Professional title</label>
        <input name="professional_title">

        <label>Professional summary</label>
        <textarea name="professional_summary"></textarea>

        <label>Education</label>
        <textarea name="education"></textarea>

        <label>Work experience</label>
        <textarea name="experience"></textarea>

        <label>Skills</label>
        <textarea name="skills"></textarea>

        <label>Certificates</label>
        <textarea name="certificates"></textarea>

        <label>Target job</label>
        <input name="target_job">

        <button class="btn green"
                type="submit">
        Submit CV Request
        </button>

        </form>

        </div>
        """
    )


# ============================================================
# FARMER
# ============================================================

@app.route(
    "/farmer/new",
    methods=["GET", "POST"]
)
@login_required
def new_farmer():

    if request.method == "POST":

        full_name = clean(
            request.form.get("full_name")
        )

        phone = clean(
            request.form.get("phone")
        )

        email = clean(
            request.form.get("email")
        )

        nrc = clean(
            request.form.get("nrc_number")
        )

        province = clean(
            request.form.get("province")
        )

        district = clean(
            request.form.get("district")
        )

        chiefdom = clean(
            request.form.get("chiefdom")
        )

        village = clean(
            request.form.get("village")
        )

        farm_name = clean(
            request.form.get("farm_name")
        )

        farm_location = clean(
            request.form.get("farm_location")
        )

        farm_size = clean(
            request.form.get("farm_size")
        )

        farming_type = clean(
            request.form.get("farming_type")
        )

        crops = clean(
            request.form.get("crops")
        )

        livestock = clean(
            request.form.get("livestock")
        )

        cooperative = clean(
            request.form.get("cooperative_name")
        )

        service_payload = {
            "user_id": current_user_id(),
            "title": "Farmer Registration",
            "description":
                f"Farmer registration for {full_name}",
            "status": "submitted",
            "priority": "normal",
            "currency": PAYMENT_CURRENCY,
        }

        service_result = insert_if_possible(
            "service_requests",
            service_payload
        )

        service_id = None

        if service_result:
            service_id = service_result[0].get(
                "id"
            )

        payload = {
            "user_id": current_user_id(),
            "service_request_id": service_id,
            "full_name": full_name,
            "phone": phone,
            "email": email,
            "nrc_number": nrc,
            "province": province,
            "district": district,
            "chiefdom": chiefdom,
            "village": village,
            "farm_name": farm_name,
            "farm_location": farm_location,
            "farm_size": farm_size or None,
            "farm_size_unit": "hectares",
            "farming_type": farming_type,
            "crops": crops,
            "livestock": livestock,
            "cooperative_name": cooperative,
            "registration_status": "submitted",
        }

        result = insert_if_possible(
            "farmer_profiles",
            payload
        )

        if result:

            log_activity(
                "farmer_registration",
                "Farmer registration request submitted.",
                service_request_id=service_id,
            )

            flash(
                "Farmer registration request submitted.",
                "success"
            )

            return redirect(
                url_for("dashboard")
            )

        flash(
            "Farmer request could not be submitted.",
            "danger"
        )

    return page(
        "Farmer Registration",
        """
        <div class="card">

        <h2>Farmer Registration Assistance</h2>

        <form method="POST">

        <label>Full name</label>
        <input name="full_name" required>

        <label>Phone</label>
        <input name="phone">

        <label>Email</label>
        <input name="email">

        <label>NRC number</label>
        <input name="nrc_number">

        <label>Province</label>
        <input name="province">

        <label>District</label>
        <input name="district">

        <label>Chiefdom</label>
        <input name="chiefdom">

        <label>Village</label>
        <input name="village">

        <label>Farm name</label>
        <input name="farm_name">

        <label>Farm location</label>
        <input name="farm_location">

        <label>Farm size (hectares)</label>
        <input
            type="number"
            step="0.01"
            name="farm_size">

        <label>Farming type</label>
        <input
            name="farming_type"
            placeholder="Crop farming, livestock, mixed...">

        <label>Crops</label>
        <textarea name="crops"></textarea>

        <label>Livestock</label>
        <textarea name="livestock"></textarea>

        <label>Cooperative</label>
        <input name="cooperative_name">

        <button class="btn green"
                type="submit">
        Submit Farmer Request
        </button>

        </form>

        </div>
        """
    )


# ============================================================
# TPIN
# ============================================================

@app.route(
    "/tpin/new",
    methods=["GET", "POST"]
)
@login_required
def new_tpin():

    if request.method == "POST":

        full_name = clean(
            request.form.get("full_name")
        )

        phone = clean(
            request.form.get("phone")
        )

        email = clean(
            request.form.get("email")
        )

        nrc = clean(
            request.form.get("nrc_number")
        )

        business_name = clean(
            request.form.get("business_name")
        )

        business_type = clean(
            request.form.get("business_type")
        )

        province = clean(
            request.form.get("province")
        )

        district = clean(
            request.form.get("district")
        )

        address = clean(
            request.form.get("address")
        )

        request_type = clean(
            request.form.get("request_type")
        ) or "individual"

        service_payload = {
            "user_id": current_user_id(),
            "title": "TPIN Assistance",
            "description":
                f"TPIN request for {full_name}",
            "status": "submitted",
            "priority": "normal",
            "currency": PAYMENT_CURRENCY,
        }

        service_result = insert_if_possible(
            "service_requests",
            service_payload
        )

        service_id = None

        if service_result:
            service_id = service_result[0].get(
                "id"
            )

        payload = {
            "user_id": current_user_id(),
            "service_request_id": service_id,
            "full_name": full_name,
            "phone": phone,
            "email": email,
            "nrc_number": nrc,
            "business_name": business_name,
            "business_type": business_type,
            "province": province,
            "district": district,
            "address": address,
            "request_type": request_type,
            "status": "submitted",
        }

        result = insert_if_possible(
            "tpin_requests",
            payload
        )

        # Older database may have tpn_requests.
        if not result:

            result = insert_if_possible(
                "tpn_requests",
                payload
            )

        if result:

            log_activity(
                "tpin_request",
                "TPIN assistance request submitted.",
                service_request_id=service_id,
            )

            flash(
                "TPIN request submitted successfully.",
                "success"
            )

            return redirect(
                url_for("dashboard")
            )

        flash(
            "TPIN request could not be submitted.",
            "danger"
        )

    return page(
        "TPIN Assistance",
        """
        <div class="card">

        <h2>TPIN Assistance</h2>

        <form method="POST">

        <label>Request type</label>

        <select name="request_type">

        <option value="individual">
        Individual
        </option>

        <option value="business">
        Business
        </option>

        <option value="farmer">
        Farmer
        </option>

        <option value="other">
        Other
        </option>

        </select>

        <label>Full name</label>
        <input name="full_name" required>

        <label>Phone</label>
        <input name="phone">

        <label>Email</label>
        <input name="email">

        <label>NRC number</label>
        <input name="nrc_number">

        <label>Business name</label>
        <input name="business_name">

        <label>Business type</label>
        <input name="business_type">

        <label>Province</label>
        <input name="province">

        <label>District</label>
        <input name="district">

        <label>Address</label>
        <textarea name="address"></textarea>

        <button class="btn green"
                type="submit">
        Submit TPIN Request
        </button>

        </form>

        </div>
        """
    )


# ============================================================
# DOCTOR BOOKING
# ============================================================

@app.route(
    "/doctor/new",
    methods=["GET", "POST"]
)
@login_required
def new_doctor():

    if request.method == "POST":

        doctor_type = clean(
            request.form.get("appointment_type")
        )

        date = clean(
            request.form.get(
                "appointment_date"
            )
        )

        start = clean(
            request.form.get("start_time")
        )

        end = clean(
            request.form.get("end_time")
        )

        location = clean(
            request.form.get("location")
        )

        notes = clean(
            request.form.get("notes")
        )

        service_payload = {
            "user_id": current_user_id(),
            "title": "Doctor Appointment",
            "description": notes,
            "status": "submitted",
            "priority": "normal",
            "currency": PAYMENT_CURRENCY,
        }

        service_result = insert_if_possible(
            "service_requests",
            service_payload
        )

        service_id = None

        if service_result:
            service_id = service_result[0].get(
                "id"
            )

        appointment = {
            "service_request_id": service_id,
            "client_id": current_user_id(),
            "appointment_type": doctor_type,
            "appointment_date": date or None,
            "start_time": start or None,
            "end_time": end or None,
            "location": location,
            "status": "pending",
            "notes": notes,
        }

        result = insert_if_possible(
            "appointments",
            appointment
        )

        if result:

            log_activity(
                "doctor_booking",
                "Doctor appointment request submitted.",
                service_request_id=service_id,
            )

            flash(
                "Doctor appointment request submitted.",
                "success"
            )

            return redirect(
                url_for("dashboard")
            )

        flash(
            "Doctor appointment could not be created.",
            "danger"
        )

    return page(
        "Doctor Booking",
        """
        <div class="card">

        <h2>Doctor Booking</h2>

        <form method="POST">

        <label>Appointment type</label>

        <select name="appointment_type">

        <option value="in_person">
        In person
        </option>

        <option value="online">
        Online
        </option>

        </select>

        <label>Date</label>
        <input
            type="date"
            name="appointment_date"
            required>

        <label>Start time</label>
        <input
            type="time"
            name="start_time">

        <label>End time</label>
        <input
            type="time"
            name="end_time">

        <label>Location</label>
        <input name="location">

        <label>Notes</label>
        <textarea name="notes"></textarea>

        <button class="btn green"
                type="submit">
        Request Doctor Appointment
        </button>

        </form>

        </div>
        """
    )


# ============================================================
# LAWYER BOOKING
# ============================================================

@app.route(
    "/lawyer/new",
    methods=["GET", "POST"]
)
@login_required
def new_lawyer():

    if request.method == "POST":

        appointment_type = clean(
            request.form.get(
                "appointment_type"
            )
        )

        date = clean(
            request.form.get(
                "appointment_date"
            )
        )

        start = clean(
            request.form.get(
                "start_time"
            )
        )

        end = clean(
            request.form.get(
                "end_time"
            )
        )

        location = clean(
            request.form.get("location")
        )

        notes = clean(
            request.form.get("notes")
        )

        service_payload = {
            "user_id": current_user_id(),
            "title": "Lawyer Consultation",
            "description": notes,
            "status": "submitted",
            "priority": "normal",
            "currency": PAYMENT_CURRENCY,
        }

        service_result = insert_if_possible(
            "service_requests",
            service_payload
        )

        service_id = None

        if service_result:
            service_id = service_result[0].get(
                "id"
            )

        appointment = {
            "service_request_id": service_id,
            "client_id": current_user_id(),
            "appointment_type": appointment_type,
            "appointment_date": date or None,
            "start_time": start or None,
            "end_time": end or None,
            "location": location,
            "status": "pending",
            "notes": notes,
        }

        result = insert_if_possible(
            "appointments",
            appointment
        )

        if result:

            log_activity(
                "lawyer_booking",
                "Lawyer consultation request submitted.",
                service_request_id=service_id,
            )

            flash(
                "Lawyer consultation request submitted.",
                "success"
            )

            return redirect(
                url_for("dashboard")
            )

        flash(
            "Lawyer request could not be created.",
            "danger"
        )

    return page(
        "Lawyer Booking",
        """
        <div class="card">

        <h2>Lawyer Consultation</h2>

        <form method="POST">

        <label>Consultation type</label>

        <select name="appointment_type">

        <option value="in_person">
        In person
        </option>

        <option value="online">
        Online
        </option>

        </select>

        <label>Date</label>
        <input
            type="date"
            name="appointment_date"
            required>

        <label>Start time</label>
        <input
            type="time"
            name="start_time">

        <label>End time</label>
        <input
            type="time"
            name="end_time">

        <label>Location</label>
        <input name="location">

        <label>Describe your legal matter</label>
        <textarea
            name="notes"
            required></textarea>

        <button class="btn green"
                type="submit">
        Request Lawyer
        </button>

        </form>

        </div>
        """
    )


# ============================================================
# DELIVERY
# ============================================================

@app.route(
    "/delivery/new",
    methods=["GET", "POST"]
)
@login_required
def new_delivery():

    if request.method == "POST":

        pickup = clean(
            request.form.get(
                "pickup_location"
            )
        )

        destination = clean(
            request.form.get(
                "destination"
            )
        )

        recipient = clean(
            request.form.get(
                "recipient_name"
            )
        )

        recipient_phone = clean(
            request.form.get(
                "recipient_phone"
            )
        )

        package = clean(
            request.form.get(
                "package_description"
            )
        )

        requested_date = clean(
            request.form.get(
                "requested_date"
            )
        )

        requested_time = clean(
            request.form.get(
                "requested_time"
            )
        )

        fee = clean(
            request.form.get(
                "delivery_fee"
            )
        ) or "0"

        service_payload = {
            "user_id": current_user_id(),
            "title": "Driver & Delivery",
            "description":
                f"{pickup} to {destination}",
            "status": "submitted",
            "priority": "normal",
            "amount": fee,
            "currency": PAYMENT_CURRENCY,
        }

        service_result = insert_if_possible(
            "service_requests",
            service_payload
        )

        service_id = None

        if service_result:
            service_id = service_result[0].get(
                "id"
            )

        payload = {
            "service_request_id": service_id,
            "customer_id": current_user_id(),
            "pickup_location": pickup,
            "destination": destination,
            "recipient_name": recipient,
            "recipient_phone": recipient_phone,
            "package_description": package,
            "delivery_fee": fee,
            "currency": PAYMENT_CURRENCY,
            "requested_date":
                requested_date or None,
            "requested_time":
                requested_time or None,
            "status": "requested",
        }

        result = insert_if_possible(
            "deliveries",
            payload
        )

        if result:

            log_activity(
                "delivery_request",
                "Delivery request submitted.",
                service_request_id=service_id,
            )

            flash(
                "Delivery request submitted.",
                "success"
            )

            return redirect(
                url_for("dashboard")
            )

        flash(
            "Delivery request could not be created.",
            "danger"
        )

    return page(
        "Delivery",
        """
        <div class="card">

        <h2>Driver & Delivery</h2>

        <form method="POST">

        <label>Pickup location</label>
        <input
            name="pickup_location"
            required>

        <label>Destination</label>
        <input
            name="destination"
            required>

        <label>Recipient name</label>
        <input name="recipient_name">

        <label>Recipient phone</label>
        <input name="recipient_phone">

        <label>Package description</label>
        <textarea
            name="package_description"></textarea>

        <label>Delivery date</label>
        <input
            type="date"
            name="requested_date">

        <label>Delivery time</label>
        <input
            type="time"
            name="requested_time">

        <label>Delivery fee (ZMW)</label>
        <input
            type="number"
            step="0.01"
            name="delivery_fee"
            value="0">

        <button class="btn green"
                type="submit">
        Request Delivery
        </button>

        </form>

        </div>
        """
    )


# ============================================================
# DOCUMENT LIBRARY
# ============================================================

@app.route("/documents")
def documents():

    docs = rest_select(
        "documents",
        {
            "is_active": "eq.true",
            "order": "created_at.desc",
            "limit": "100",
        }
    ) or []

    # If old table is empty, try document_records.
    if not docs:

        docs = rest_select(
            "document_records",
            {
                "order": "created_at.desc",
                "limit": "100",
            }
        ) or []

    rows = ""

    for doc in docs:

        rows += f"""
        <tr>

        <td>
        {clean(doc.get('title'))}
        </td>

        <td>
        {clean(doc.get('subject'))}
        </td>

        <td>
        {clean(doc.get('course'))}
        </td>

        <td>
        {clean(doc.get('class_level'))}
        </td>

        <td>
        <a class="btn small"
           href="/document/{doc.get('id')}">
           View
        </a>
        </td>

        </tr>
        """

    if not rows:

        rows = """
        <tr>
        <td colspan="5">
        No documents available.
        </td>
        </tr>
        """

    return page(
        "Document Library",
        f"""
        <div class="card">

        <h2>KOJA Academic Resources</h2>

        <table>

        <tr>
        <th>Title</th>
        <th>Subject</th>
        <th>Course</th>
        <th>Class</th>
        <th></th>
        </tr>

        {rows}

        </table>

        </div>
        """
    )


@app.route("/document/<document_id>")
def document(document_id):

    doc = first_row(
        "documents",
        {
            "id": f"eq.{document_id}"
        }
    )

    table = "documents"

    if not doc:

        doc = first_row(
            "document_records",
            {
                "id": f"eq.{document_id}"
            }
        )

        table = "document_records"

    if not doc:
        abort(404)

    return page(
        "Document",
        f"""
        <div class="card">

        <h2>
        {clean(doc.get('title'))}
        </h2>

        <p>
        {clean(doc.get('description'))}
        </p>

        <p>
        <strong>Subject:</strong>
        {clean(doc.get('subject'))}
        </p>

        <p>
        <strong>Course:</strong>
        {clean(doc.get('course'))}
        </p>

        <p>
        <strong>Class:</strong>
        {clean(doc.get('class_level'))}
        </p>

        <p>
        <strong>File:</strong>
        {clean(doc.get('file_name'))}
        </p>

        {
            (
                f'<a class="btn green" '
                f'href="/document/download/{doc.get("id")}">'
                f'Download</a>'
            )
            if doc.get("file_path")
            else
            '<p>File is not currently available.</p>'
        }

        </div>
        """
    )


@app.route(
    "/document/download/<document_id>"
)
@login_required
def download_document(document_id):

    doc = first_row(
        "documents",
        {
            "id": f"eq.{document_id}"
        }
    )

    if not doc:
        doc = first_row(
            "document_records",
            {
                "id": f"eq.{document_id}"
            }
        )

    if not doc:
        abort(404)

    path = (
        doc.get("file_path")
        or doc.get("storage_path")
    )

    if not path:
        abort(404)

    data, content_type = storage_download(
        path
    )

    if not data:
        flash(
            "Document could not be downloaded.",
            "danger"
        )
        return redirect(
            url_for("documents")
        )

    filename = (
        doc.get("file_name")
        or doc.get("original_filename")
        or "KOJA-document"
    )

    log_activity(
        "document_download",
        f"Downloaded {filename}."
    )

    return send_file(
        io.BytesIO(data),
        mimetype=content_type,
        as_attachment=True,
        download_name=filename,
    )


# ============================================================
# ADMIN DASHBOARD
# ============================================================

@app.route("/admin")
@admin_required
def admin_dashboard():

    service_requests = rest_select(
        "service_requests",
        {
            "order": "created_at.desc",
            "limit": "100",
        }
    ) or []

    assignments = rest_select(
        "assignment_requests",
        {
            "order": "created_at.desc",
            "limit": "100",
        }
    ) or []

    payments = rest_select(
        "payments",
        {
            "order": "created_at.desc",
            "limit": "100",
        }
    ) or []

    rows = ""

    for item in service_requests:

        rid = item.get("id")

        rows += f"""
        <tr>

        <td>
        {clean(item.get('title'))}
        </td>

        <td>
        {clean(item.get('status'))}
        </td>

        <td>
        {clean(item.get('priority'))}
        </td>

        <td>
        {clean(item.get('created_at'))}
        </td>

        <td>

        <a class="btn small"
           href="/admin/request/{rid}">
           Manage
        </a>

        </td>

        </tr>
        """

    if not rows:
        rows = """
        <tr>
        <td colspan="5">
        No service requests.
        </td>
        </tr>
        """

    return page(
        "Admin Dashboard",
        f"""
        <section class="hero">

        <h1>KOJA AFRICA ADMIN</h1>

        <p>
        Administrator Control Centre
        </p>

        </section>

        <div class="grid">

        <div class="card">
        <h3>Service Requests</h3>
        <h2>{len(service_requests)}</h2>
        </div>

        <div class="card">
        <h3>Assignments</h3>
        <h2>{len(assignments)}</h2>
        </div>

        <div class="card">
        <h3>Payments</h3>
        <h2>{len(payments)}</h2>
        </div>

        </div>

        <div class="card">

        <h2>Service Requests</h2>

        <table>

        <tr>
        <th>Title</th>
        <th>Status</th>
        <th>Priority</th>
        <th>Date</th>
        <th></th>
        </tr>

        {rows}

        </table>

        </div>
        """
    )


# ============================================================
# ADMIN REQUEST MANAGEMENT
# ============================================================

@app.route(
    "/admin/request/<request_id>",
    methods=["GET", "POST"]
)
@admin_required
def admin_request(request_id):

    item = first_row(
        "service_requests",
        {
            "id": f"eq.{request_id}"
        }
    )

    if not item:
        abort(404)

    old_status = item.get(
        "status",
        "submitted"
    )

    if request.method == "POST":

        status = clean(
            request.form.get("status")
        )

        admin_notes = clean(
            request.form.get("admin_notes")
        )

        update = {
            "status": status,
            "admin_notes": admin_notes,
        }

        result = rest_update(
            "service_requests",
            {
                "id": f"eq.{request_id}"
            },
            update
        )

        if result:

            log_activity(
                "admin_update_request",
                "Administrator updated service request.",
                service_request_id=request_id,
                old_status=old_status,
                new_status=status,
            )

            # Notify client.
            uid = item.get("user_id")

            if uid:

                rest_insert(
                    "notifications",
                    {
                        "user_id": uid,
                        "service_request_id":
                            request_id,
                        "title":
                            "Service Request Updated",
                        "message":
                            (
                                f"Your request status is now "
                                f"{status}."
                            ),
                        "notification_type":
                            "service_update",
                    }
                )

            flash(
                "Service request updated.",
                "success"
            )

            return redirect(
                url_for(
                    "admin_request",
                    request_id=request_id
                )
            )

        flash(
            "Could not update request.",
            "danger"
        )

    return page(
        "Manage Request",
        f"""
        <div class="card">

        <h2>
        {clean(item.get('title'))}
        </h2>

        <p>
        {clean(item.get('description'))}
        </p>

        <p>
        <strong>User:</strong>
        {clean(item.get('user_id'))}
        </p>

        <p>
        <strong>Current status:</strong>
        {clean(item.get('status'))}
        </p>

        <form method="POST">

        <label>Status</label>

        <select name="status">

        <option value="submitted">
        Submitted
        </option>

        <option value="under_review">
        Under Review
        </option>

        <option value="information_required">
        Information Required
        </option>

        <option value="assigned">
        Assigned
        </option>

        <option value="accepted">
        Accepted
        </option>

        <option value="in_progress">
        In Progress
        </option>

        <option value="scheduled">
        Scheduled
        </option>

        <option value="completed">
        Completed
        </option>

        <option value="cancelled">
        Cancelled
        </option>

        <option value="rejected">
        Rejected
        </option>

        </select>

        <label>Administrator notes</label>

        <textarea
            name="admin_notes">
        {clean(item.get('admin_notes'))}
        </textarea>

        <button
            class="btn green"
            type="submit">
        Save Changes
        </button>

        </form>

        </div>
        """
    )


# ============================================================
# ADMIN ASSIGNMENTS
# ============================================================

@app.route("/admin/assignments")
@admin_required
def admin_assignments():

    assignments = rest_select(
        "assignment_requests",
        {
            "order": "created_at.desc",
            "limit": "100",
        }
    ) or []

    rows = ""

    for item in assignments:

        rows += f"""
        <tr>

        <td>
        {clean(item.get('assignment_title'))}
        </td>

        <td>
        {clean(item.get('subject'))}
        </td>

        <td>
        {clean(item.get('course'))}
        </td>

        <td>
        {clean(item.get('status'))}
        </td>

        <td>
        {clean(item.get('created_at'))}
        </td>

        </tr>
        """

    return page(
        "Admin Assignments",
        f"""
        <div class="card">

        <h2>Assignment Requests</h2>

        <table>

        <tr>
        <th>Title</th>
        <th>Subject</th>
        <th>Course</th>
        <th>Status</th>
        <th>Date</th>
        </tr>

        {rows}

        </table>

        </div>
        """
    )


# ============================================================
# ADMIN DOCUMENT UPLOAD
# ============================================================

@app.route(
    "/admin/documents/new",
    methods=["GET", "POST"]
)
@admin_required
def admin_document_upload():

    if request.method == "POST":

        title = clean(
            request.form.get("title")
        )

        description = clean(
            request.form.get("description")
        )

        subject = clean(
            request.form.get("subject")
        )

        course = clean(
            request.form.get("course")
        )

        class_level = clean(
            request.form.get("class_level")
        )

        file = request.files.get("file")

        if not title or not file:
            flash(
                "Title and file are required.",
                "danger"
            )
            return redirect(
                url_for(
                    "admin_document_upload"
                )
            )

        if not allowed_file(
            file.filename
        ):
            flash(
                "File type is not supported.",
                "danger"
            )
            return redirect(
                url_for(
                    "admin_document_upload"
                )
            )

        file_bytes = file.read()

        if not file_bytes:
            flash(
                "The uploaded file is empty.",
                "danger"
            )
            return redirect(
                url_for(
                    "admin_document_upload"
                )
            )

        path = upload_storage(
            file.filename,
            file_bytes,
            file.content_type
            or "application/octet-stream"
        )

        if not path:
            flash(
                "File upload failed.",
                "danger"
            )
            return redirect(
                url_for(
                    "admin_document_upload"
                )
            )

        payload = {
            "title": title,
            "description": description,
            "subject": subject,
            "course": course,
            "class_level": class_level,
            "file_name": file.filename,
            "file_path": path,
            "file_size": len(file_bytes),
            "mime_type":
                file.content_type
                or "application/octet-stream",
            "uploaded_by":
                current_user_id(),
            "is_public": True,
            "is_active": True,
        }

        result = insert_if_possible(
            "documents",
            payload
        )

        if result:

            flash(
                "Document uploaded successfully.",
                "success"
            )

            return redirect(
                url_for("documents")
            )

        flash(
            "Document database record could not be created.",
            "danger"
        )

    return page(
        "Upload Document",
        """
        <div class="card">

        <h2>Upload Academic Document</h2>

        <form
            method="POST"
            enctype="multipart/form-data">

        <label>Title</label>
        <input name="title" required>

        <label>Description</label>
        <textarea name="description"></textarea>

        <label>Subject</label>
        <input name="subject">

        <label>Course</label>
        <input name="course">

        <label>Class level</label>
        <input name="class_level">

        <label>File</label>
        <input
            type="file"
            name="file"
            required>

        <button
            class="btn green"
            type="submit">
        Upload Document
        </button>

        </form>

        </div>
        """
    )


# ============================================================
# HEALTH CHECK
# ============================================================

@app.route("/health")
def health():

    config_error = configuration_error()

    if config_error:

        return {
            "status": "error",
            "message": config_error,
        }, 500

    return {
        "status": "ok",
        "application": "KOJA AFRICA",
        "database": "Supabase REST",
        "timestamp":
            datetime.now(
                timezone.utc
            ).isoformat(),
    }


# ============================================================
# DATABASE TEST
# ============================================================

@app.route("/database-test")
def database_test():

    if not SUPABASE_URL or not SUPABASE_KEY:

        return {
            "connected": False,
            "error":
                "SUPABASE_URL or SUPABASE_KEY is missing."
        }, 500

    results = {}

    tables = [
        "service_categories",
        "service_requests",
        "service_providers",
        "assignment_requests",
        "cv_requests",
        "farmer_profiles",
        "tpin_requests",
        "appointments",
        "deliveries",
        "payments",
        "notifications",
        "documents",
        "profiles",
        "questions",
        "answers",
    ]

    for table in tables:

        results[table] = table_exists(
            table
        )

    return {
        "connected": True,
        "tables": results,
    }


# ============================================================
# ERROR HANDLERS
# ============================================================

@app.errorhandler(404)
def not_found(error):

    return page(
        "Not Found",
        """
        <div class="card">

        <h2>Page not found</h2>

        <p>
        The KOJA Africa page you requested does not exist.
        </p>

        <a class="btn"
           href="/">
           Return Home
        </a>

        </div>
        """
    ), 404


@app.errorhandler(413)
def too_large(error):

    return page(
        "File Too Large",
        """
        <div class="card">

        <h2>File too large</h2>

        <p>
        The maximum upload size is 20 MB.
        </p>

        </div>
        """
    ), 413


@app.errorhandler(500)
def server_error(error):

    logger.exception(
        "Unhandled KOJA error"
    )

    return page(
        "Server Error",
        """
        <div class="card">

        <h2>KOJA Africa encountered an error.</h2>

        <p>
        Please check the Render logs for the exact error.
        </p>

        </div>
        """
    ), 500


# ============================================================
# STARTUP
# ============================================================

@app.context_processor
def inject_globals():

    return {
        "current_user":
            current_user(),
        "current_email":
            current_email(),
        "is_admin":
            is_admin(),
    }


if __name__ == "__main__":

    port = int(
        os.getenv(
            "PORT",
            "5000"
        )
    )

    host = os.getenv(
        "HOST",
        "0.0.0.0"
    )

    logger.info(
        "Starting KOJA AFRICA on %s:%s",
        host,
        port
    )

    app.run(
        host=host,
        port=port,
        debug=False
    )

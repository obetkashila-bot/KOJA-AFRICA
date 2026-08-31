import os
import io
import uuid
import json
import logging
from datetime import datetime, timezone
from functools import wraps
from urllib.parse import quote

from flask import (
    Flask,
    request,
    redirect,
    url_for,
    session,
    flash,
    get_flashed_messages,
    jsonify,
    send_file,
    render_template_string,
)

# ============================================================
# KOJA AFRICA
# COMPLETE FLASK APPLICATION
# ============================================================
#
# Architecture:
#   Flask
#   Supabase Auth
#   Supabase PostgreSQL REST API
#   Supabase Storage
#   Render
#
# Authentication:
#   Email + password
#
# Main modules:
#   Authentication
#   Profiles
#   Dashboard
#   Assignments
#   Questions
#   Answers
#   Documents
#   Farmer services
#   Driver registration
#   Driver online status
#   Driver GPS
#   Nearby drivers
#   Delivery requests
#   Delivery tracking
#   Notifications
#   Admin dashboard
#   Health monitoring
#
# IMPORTANT:
# The application does NOT use psycopg or psycopg2.
# ============================================================


load_dotenv()

logging.basicConfig(
    level=logging.INFO
)

logger = logging.getLogger(
    "koja-africa"
)


# ============================================================
# FLASK
# ============================================================

app = Flask(__name__)

app.secret_key = (
    os.getenv("SECRET_KEY")
    or "change-this-secret-key"
)

app.config["MAX_CONTENT_LENGTH"] = (
    15 * 1024 * 1024
)


# ============================================================
# ENVIRONMENT
# ============================================================

SUPABASE_URL = os.getenv(
    "SUPABASE_URL",
    ""
).rstrip("/")

SUPABASE_ANON_KEY = os.getenv(
    "SUPABASE_ANON_KEY",
    ""
).strip()

SUPABASE_SERVICE_KEY = os.getenv(
    "SUPABASE_SERVICE_KEY",
    ""
).strip()

STORAGE_BUCKET = os.getenv(
    "SUPABASE_STORAGE_BUCKET",
    "koja-files"
)

APP_NAME = "KOJA AFRICA"

APP_TAGLINE = (
    "Knowledge • Questions • Answers"
)


# ============================================================
# TABLE NAMES
# ============================================================

TABLE_PROFILES = "profiles"

TABLE_ASSIGNMENTS = "assignments"

TABLE_ASSIGNMENT_ANSWERS = (
    "assignment_answers"
)

TABLE_QUESTIONS = "questions"

TABLE_ANSWERS = "answers"

TABLE_DOCUMENTS = "documents"

TABLE_FARMERS = "farmers"

TABLE_DRIVERS = "drivers"

TABLE_DRIVER_LOCATIONS = (
    "driver_locations"
)

TABLE_DELIVERY_REQUESTS = (
    "delivery_requests"
)

TABLE_NOTIFICATIONS = (
    "notifications"
)

TABLE_ACTIVITY_LOGS = (
    "activity_logs"
)


# ============================================================
# CONFIGURATION
# ============================================================

DEFAULT_ANSWER_PRICE = os.getenv(
    "KOJA_PAYMENT_AMOUNT",
    "10.00"
)

PAYMENT_CURRENCY = os.getenv(
    "PAYMENT_CURRENCY",
    "ZMW"
)


# ============================================================
# BASIC HELPERS
# ============================================================

def utc_now():

    return datetime.now(
        timezone.utc
    ).isoformat()


def configured():

    return bool(
        SUPABASE_URL
        and (
            SUPABASE_SERVICE_KEY
            or SUPABASE_ANON_KEY
        )
    )


def database_key():

    return (
        SUPABASE_SERVICE_KEY
        or SUPABASE_ANON_KEY
    )


def auth_key():

    return (
        SUPABASE_ANON_KEY
        or SUPABASE_SERVICE_KEY
    )


def auth_headers(token=None):

    key = auth_key()

    headers = {
        "apikey": key,
        "Content-Type":
            "application/json",
    }

    if token:

        headers["Authorization"] = (
            f"Bearer {token}"
        )

    else:

        headers["Authorization"] = (
            f"Bearer {key}"
        )

    return headers


def db_headers(token=None):

    key = database_key()

    headers = {
        "apikey": key,
        "Content-Type":
            "application/json",
    }

    if token:

        headers["Authorization"] = (
            f"Bearer {token}"
        )

    else:

        headers["Authorization"] = (
            f"Bearer {key}"
        )

    return headers


def auth_url(path):

    return (
        f"{SUPABASE_URL}/auth/v1/"
        f"{path.lstrip('/')}"
    )


def table_url(table):

    return (
        f"{SUPABASE_URL}/rest/v1/"
        f"{table}"
    )


def storage_url(path):

    return (
        f"{SUPABASE_URL}"
        f"/storage/v1/object/"
        f"{path.lstrip('/')}"
    )


def safe_json(response):

    try:

        return response.json()

    except Exception:

        return {}


def error_text(response):

    data = safe_json(
        response
    )

    if isinstance(data, dict):

        return (
            data.get("message")
            or data.get("msg")
            or data.get(
                "error_description"
            )
            or data.get("error")
            or (
                f"HTTP "
                f"{response.status_code}"
            )
        )

    return (
        f"HTTP "
        f"{response.status_code}"
    )


# ============================================================
# SESSION
# ============================================================

def user():

    return session.get("user")


def user_id():

    current = user()

    if not current:
        return None

    return current.get("id")


def token():

    return session.get(
        "access_token"
    )


def admin_user():

    current = user()

    if not current:
        return False

    role = (
        current.get("role")
        or current.get(
            "user_metadata",
            {}
        ).get("role")
        or current.get(
            "app_metadata",
            {}
        ).get("role")
    )

    admin_emails = {
        x.strip().lower()
        for x in os.getenv(
            "KOJA_ADMIN_EMAILS",
            ""
        ).split(",")
        if x.strip()
    }

    email = (
        current.get("email")
        or ""
    ).lower()

    return (
        role == "admin"
        or email in admin_emails
    )


def login_required(fn):

    @wraps(fn)
    def wrapper(*args, **kwargs):

        if not user():

            flash(
                "Please log in first.",
                "error"
            )

            return redirect(
                url_for("login")
            )

        return fn(
            *args,
            **kwargs
        )

    return wrapper


def admin_required(fn):

    @wraps(fn)
    def wrapper(*args, **kwargs):

        if not user():

            return redirect(
                url_for("login")
            )

        if not admin_user():

            flash(
                "Administrator access required.",
                "error"
            )

            return redirect(
                url_for("dashboard")
            )

        return fn(
            *args,
            **kwargs
        )

    return wrapper


# ============================================================
# SUPABASE AUTH
# ============================================================

def signup(
    email,
    password,
    full_name
):

    return requests.post(

        auth_url("signup"),

        headers=auth_headers(),

        json={
            "email": email,
            "password": password,
            "data": {
                "full_name":
                    full_name
            },
        },

        timeout=25
    )


def signin(
    email,
    password
):

    return requests.post(

        auth_url(
            "token?grant_type=password"
        ),

        headers=auth_headers(),

        json={
            "email": email,
            "password": password,
        },

        timeout=25
    )


def auth_logout():

    current_token = token()

    if not current_token:
        return

    try:

        requests.post(

            auth_url("logout"),

            headers=auth_headers(
                current_token
            ),

            timeout=10
        )

    except Exception:

        logger.exception(
            "Logout request failed"
        )


# ============================================================
# SUPABASE REST
# ============================================================

def db_select(
    table,
    params=None,
    token_value=None
):

    if not configured():

        return None, (
            "Supabase is not configured."
        )

    try:

        response = requests.get(

            table_url(table),

            headers=db_headers(
                token_value
            ),

            params=params or {},

            timeout=25
        )

        if response.status_code >= 400:

            return None, error_text(
                response
            )

        return safe_json(
            response
        ), None

    except Exception as exc:

        logger.exception(
            "Database SELECT failed"
        )

        return None, str(exc)


def db_insert(
    table,
    data,
    token_value=None
):

    if not configured():

        return None, (
            "Supabase is not configured."
        )

    try:

        headers = db_headers(
            token_value
        )

        headers["Prefer"] = (
            "return=representation"
        )

        response = requests.post(

            table_url(table),

            headers=headers,

            json=data,

            timeout=25
        )

        if response.status_code >= 400:

            return None, error_text(
                response
            )

        return safe_json(
            response
        ), None

    except Exception as exc:

        logger.exception(
            "Database INSERT failed"
        )

        return None, str(exc)


def db_update(
    table,
    params,
    data,
    token_value=None
):

    if not configured():

        return None, (
            "Supabase is not configured."
        )

    try:

        headers = db_headers(
            token_value
        )

        headers["Prefer"] = (
            "return=representation"
        )

        response = requests.patch(

            table_url(table),

            headers=headers,

            params=params,

            json=data,

            timeout=25
        )

        if response.status_code >= 400:

            return None, error_text(
                response
            )

        return safe_json(
            response
        ), None

    except Exception as exc:

        logger.exception(
            "Database UPDATE failed"
        )

        return None, str(exc)


def db_delete(
    table,
    params,
    token_value=None
):

    if not configured():

        return None, (
            "Supabase is not configured."
        )

    try:

        response = requests.delete(

            table_url(table),

            headers=db_headers(
                token_value
            ),

            params=params,

            timeout=25
        )

        if response.status_code >= 400:

            return None, error_text(
                response
            )

        return True, None

    except Exception as exc:

        logger.exception(
            "Database DELETE failed"
        )

        return None, str(exc)


# ============================================================
# FLEXIBLE DATABASE INSERT
# ============================================================

def flexible_insert(
    table,
    candidates
):

    """
    Attempts candidate payloads in sequence.

    This allows the application to work with
    existing tables whose exact optional columns
    differ.
    """

    last_error = None

    for payload in candidates:

        result, error = db_insert(
            table,
            payload
        )

        if error is None:

            return result, None

        last_error = error

        logger.warning(
            "Insert attempt failed for %s: %s",
            table,
            error
        )

    return None, last_error


# ============================================================
# STORAGE
# ============================================================

def storage_upload(
    file_bytes,
    path,
    content_type
):

    if not SUPABASE_SERVICE_KEY:

        return None, (
            "SUPABASE_SERVICE_KEY "
            "is required for storage uploads."
        )

    try:

        url = storage_url(
            f"{STORAGE_BUCKET}/{path}"
        )

        headers = {
            "Authorization":
                f"Bearer "
                f"{SUPABASE_SERVICE_KEY}",
            "apikey":
                SUPABASE_SERVICE_KEY,
            "Content-Type":
                content_type,
            "x-upsert":
                "true",
        }

        response = requests.post(

            url,

            headers=headers,

            data=file_bytes,

            timeout=60
        )

        if response.status_code >= 400:

            return None, error_text(
                response
            )

        public_path = (
            f"{SUPABASE_URL}"
            f"/storage/v1/object/public/"
            f"{STORAGE_BUCKET}/{path}"
        )

        return public_path, None

    except Exception as exc:

        logger.exception(
            "Storage upload failed"
        )

        return None, str(exc)


# ============================================================
# ACTIVITY LOG
# ============================================================

def activity(
    action,
    description=""
):

    uid = user_id()

    if not uid:
        return

    candidates = [

        {
            "user_id": uid,
            "action": action,
            "description":
                description,
            "ip_address":
                request.remote_addr,
            "user_agent":
                request.headers.get(
                    "User-Agent",
                    ""
                ),
        },

        {
            "user_id": uid,
            "action": action,
            "description":
                description,
        },

    ]

    try:

        flexible_insert(
            TABLE_ACTIVITY_LOGS,
            candidates
        )

    except Exception:

        logger.exception(
            "Activity log failed"
        )


# ============================================================
# PROFILE CREATION
# ============================================================

def create_profile(
    auth_user,
    full_name
):

    uid = auth_user.get("id")

    if not uid:
        return

    candidates = [

        {
            "id": uid,
            "full_name":
                full_name,
            "email":
                auth_user.get(
                    "email"
                ),
        },

        {
            "user_id": uid,
            "full_name":
                full_name,
            "email":
                auth_user.get(
                    "email"
                ),
        },

    ]

    result, error = (
        flexible_insert(
            TABLE_PROFILES,
            candidates
        )
    )

    if error:

        logger.warning(
            "Profile creation skipped: %s",
            error
        )


# ============================================================
# HTML / CSS
# ============================================================

CSS = """

* {
    box-sizing: border-box;
}

body {
    margin: 0;
    background: #f4f7f5;
    color: #172033;
    font-family: Arial, Helvetica, sans-serif;
}

.nav {
    background: #14532d;
    color: white;
}

.nav-inner {
    width: min(1150px, calc(100% - 28px));
    margin: auto;
    min-height: 64px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 15px;
}

.logo {
    color: white;
    text-decoration: none;
    font-size: 21px;
    font-weight: 800;
}

.navlinks {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
}

.navlinks a {
    color: white;
    text-decoration: none;
    padding: 9px 11px;
    border-radius: 8px;
}

.navlinks a:hover {
    background: rgba(255,255,255,.12);
}

.container {
    width: min(1150px, calc(100% - 28px));
    margin: 25px auto 55px;
}

.hero {
    background:
        linear-gradient(
            135deg,
            #14532d,
            #166534
        );
    color: white;
    padding: 34px 25px;
    border-radius: 18px;
}

.hero h1 {
    margin-top: 0;
    font-size: 38px;
}

.hero p {
    line-height: 1.6;
}

.card {
    background: white;
    border: 1px solid #e3e8e5;
    border-radius: 16px;
    padding: 23px;
    box-shadow:
        0 5px 18px
        rgba(0,0,0,.04);
}

.grid {
    display: grid;
    grid-template-columns:
        repeat(3, 1fr);
    gap: 16px;
}

.service {
    background: white;
    border: 1px solid #e3e8e5;
    border-radius: 15px;
    padding: 20px;
}

.service h2 {
    margin-top: 0;
}

.form {
    width: min(570px, 100%);
    margin: auto;
}

label {
    display: block;
    font-weight: 700;
    margin: 14px 0 6px;
}

input,
textarea,
select {
    width: 100%;
    padding: 12px;
    border:
        1px solid
        #cfd8d3;
    border-radius: 9px;
    font: inherit;
    background: white;
}

textarea {
    min-height: 140px;
    resize: vertical;
}

button,
.btn {
    display: inline-block;
    border: 0;
    background: #14532d;
    color: white;
    padding: 11px 17px;
    border-radius: 9px;
    text-decoration: none;
    cursor: pointer;
    font-weight: 700;
}

.btn:hover,
button:hover {
    background: #166534;
}

.btn-light {
    background: white;
    color: #14532d;
}

.actions {
    display: flex;
    flex-wrap: wrap;
    gap: 9px;
    margin-top: 18px;
}

.alert {
    padding: 12px 14px;
    border-radius: 9px;
    margin-bottom: 14px;
}

.alert.error {
    background: #fef3f2;
    color: #b42318;
    border: 1px solid #fecdca;
}

.alert.success {
    background: #ecfdf3;
    color: #067647;
    border: 1px solid #abefc6;
}

.alert.info {
    background: #eff8ff;
    color: #175cd3;
    border: 1px solid #b2ddff;
}

.muted {
    color: #667085;
}

.badge {
    display: inline-block;
    padding: 5px 10px;
    border-radius: 20px;
    background: #ecfdf3;
    color: #067647;
    font-size: 13px;
    font-weight: 700;
}

.stat {
    text-align: center;
    padding: 20px;
    background: white;
    border: 1px solid #e3e8e5;
    border-radius: 14px;
}

.stat-number {
    font-size: 30px;
    font-weight: 800;
}

.table-wrap {
    overflow-x: auto;
}

table {
    width: 100%;
    border-collapse: collapse;
}

th,
td {
    padding: 11px;
    border-bottom:
        1px solid
        #e5e7eb;
    text-align: left;
}

.footer {
    text-align: center;
    color: #667085;
    padding: 28px;
}

@media (max-width: 800px) {

    .grid {
        grid-template-columns: 1fr;
    }

    .nav-inner {
        flex-direction: column;
        align-items: flex-start;
        padding: 12px 0;
    }

    .hero h1 {
        font-size: 30px;
    }
}

"""


# ============================================================
# PAGE
# ============================================================

def page(
    title,
    body
):

    current = user()

    if current:

        navigation = f"""
        <a href="{url_for('dashboard')}">
            Dashboard
        </a>

        <a href="{url_for('services')}">
            Services
        </a>

        <a href="{url_for('profile')}">
            Profile
        </a>

        <a href="{url_for('notifications')}">
            Notifications
        </a>

        <a href="{url_for('logout')}">
            Logout
        </a>
        """

        home = url_for(
            "dashboard"
        )

    else:

        navigation = f"""
        <a href="{url_for('home')}">
            Home
        </a>

        <a href="{url_for('login')}">
            Login
        </a>

        <a href="{url_for('register')}">
            Register
        </a>
        """

        home = url_for(
            "home"
        )

    flashes = ""

    for category, message in (
        get_flashed_messages(
            with_categories=True
        )
    ):

        flashes += f"""
        <div class="alert {category}">
            {message}
        </div>
        """

    admin_link = ""

    if admin_user():

        admin_link = f"""
        <a href="{url_for('admin_dashboard')}">
            Admin
        </a>
        """

    navigation += admin_link

    return f"""
<!DOCTYPE html>

<html lang="en">

<head>

<meta charset="UTF-8">

<meta
    name="viewport"
    content="width=device-width,
             initial-scale=1.0"
>

<title>
{title} | {APP_NAME}
</title>

<style>
{CSS}
</style>

</head>

<body>

<nav class="nav">

<div class="nav-inner">

<a
    class="logo"
    href="{home}"
>
{APP_NAME}
</a>

<div class="navlinks">
{navigation}
</div>

</div>

</nav>

<main class="container">

{flashes}

{body}

</main>

<footer class="footer">

<strong>
{APP_NAME}
</strong>

<br>

{APP_TAGLINE}

</footer>

</body>

</html>
"""


# ============================================================
# HOME
# ============================================================

@app.route("/")
def home():

    return page(

        "Home",

        """
<section class="hero">

<h1>
KOJA AFRICA
</h1>

<p>
Knowledge • Questions • Answers
</p>

<p>
A digital platform connecting
students, farmers, drivers,
businesses and service users.
</p>

<div class="actions">

<a
    class="btn btn-light"
    href="/register"
>
Create Account
</a>

<a
    class="btn btn-light"
    href="/login"
>
Login
</a>

</div>

</section>

<br>

<section class="grid">

<div class="service">
<h2>📚</h2>
<h3>Academic Services</h3>
<p class="muted">
Assignments, questions,
answers and documents.
</p>
</div>

<div class="service">
<h2>🌾</h2>
<h3>Farmer Services</h3>
<p class="muted">
Farmer registration and
agricultural services.
</p>
</div>

<div class="service">
<h2>🚚</h2>
<h3>Delivery</h3>
<p class="muted">
Nearby drivers, requests
and delivery tracking.
</p>
</div>

</section>
"""
    )


# ============================================================
# HEALTH
# ============================================================

@app.route("/health")
def health():

    return jsonify({

        "status": "ok",

        "application":
            APP_NAME,

        "supabase":
            configured(),

        "database":
            "supabase_rest",

        "authentication":
            "supabase_auth",

        "version":
            "koja-full-v1",

    })


# ============================================================
# REGISTER
# ============================================================

@app.route(
    "/register",
    methods=["GET", "POST"]
)
def register():

    if user():

        return redirect(
            url_for("dashboard")
        )

    if request.method == "POST":

        full_name = (
            request.form.get(
                "full_name",
                ""
            ).strip()
        )

        email = (
            request.form.get(
                "email",
                ""
            ).strip().lower()
        )

        password = (
            request.form.get(
                "password",
                ""
            )
        )

        confirm = (
            request.form.get(
                "confirm_password",
                ""
            )
        )

        if not full_name:

            flash(
                "Full name is required.",
                "error"
            )

        elif not email:

            flash(
                "Email is required.",
                "error"
            )

        elif len(password) < 6:

            flash(
                "Password must be at least 6 characters.",
                "error"
            )

        elif password != confirm:

            flash(
                "Passwords do not match.",
                "error"
            )

        elif not configured():

            flash(
                "Supabase environment variables are missing.",
                "error"
            )

        else:

            try:

                response = signup(
                    email,
                    password,
                    full_name
                )

                if response.status_code not in (
                    200,
                    201
                ):

                    flash(
                        error_text(
                            response
                        ),
                        "error"
                    )

                else:

                    data = safe_json(
                        response
                    )

                    auth_user = (
                        data.get("user")
                        or {}
                    )

                    access_token = (
                        data.get(
                            "access_token"
                        )
                    )

                    if access_token:

                        session.permanent = True

                        session[
                            "access_token"
                        ] = access_token

                        session[
                            "refresh_token"
                        ] = data.get(
                            "refresh_token"
                        )

                        session[
                            "user"
                        ] = {

                            "id":
                                auth_user.get(
                                    "id"
                                ),

                            "email":
                                auth_user.get(
                                    "email",
                                    email
                                ),

                            "full_name":
                                full_name,

                        }

                        create_profile(
                            auth_user,
                            full_name
                        )

                        activity(
                            "register",
                            "New account created."
                        )

                        flash(
                            "Account created successfully.",
                            "success"
                        )

                        return redirect(
                            url_for(
                                "dashboard"
                            )
                        )

                    flash(
                        "Account created. Check your email for confirmation before logging in.",
                        "success"
                    )

                    return redirect(
                        url_for("login")
                    )

            except Exception:

                logger.exception(
                    "Registration failed"
                )

                flash(
                    "Registration failed. Check the Render logs.",
                    "error"
                )

    return page(

        "Create Account",

        """
<section class="card form">

<h1>
Create KOJA Account
</h1>

<p class="muted">
Use your email and password.
</p>

<form method="POST">

<label>
Full Name
</label>

<input
    type="text"
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
    autocomplete="email"
>

<label>
Password
</label>

<input
    type="password"
    name="password"
    minlength="6"
    required
>

<label>
Confirm Password
</label>

<input
    type="password"
    name="confirm_password"
    minlength="6"
    required
>

<br>

<button type="submit">
Create Account
</button>

</form>

<p class="muted">
Already registered?
<a href="/login">
Login
</a>
</p>

</section>
"""
    )


# ============================================================
# LOGIN
# ============================================================

@app.route(
    "/login",
    methods=["GET", "POST"]
)
def login():

    if user():

        return redirect(
            url_for("dashboard")
        )

    if request.method == "POST":

        email = (
            request.form.get(
                "email",
                ""
            ).strip().lower()
        )

        password = (
            request.form.get(
                "password",
                ""
            )
        )

        if not email or not password:

            flash(
                "Email and password are required.",
                "error"
            )

        elif not configured():

            flash(
                "Supabase environment variables are missing.",
                "error"
            )

        else:

            try:

                response = signin(
                    email,
                    password
                )

                if response.status_code != 200:

                    flash(
                        error_text(
                            response
                        ),
                        "error"
                    )

                else:

                    data = safe_json(
                        response
                    )

                    auth_user = (
                        data.get("user")
                        or {}
                    )

                    metadata = (
                        auth_user.get(
                            "user_metadata"
                        )
                        or {}
                    )

                    session.permanent = True

                    session[
                        "access_token"
                    ] = data.get(
                        "access_token"
                    )

                    session[
                        "refresh_token"
                    ] = data.get(
                        "refresh_token"
                    )

                    session[
                        "user"
                    ] = {

                        "id":
                            auth_user.get(
                                "id"
                            ),

                        "email":
                            auth_user.get(
                                "email",
                                email
                            ),

                        "full_name":
                            metadata.get(
                                "full_name"
                            )
                            or auth_user.get(
                                "email",
                                email
                            ),

                        "role":
                            metadata.get(
                                "role"
                            ),

                        "user_metadata":
                            metadata,

                        "app_metadata":
                            auth_user.get(
                                "app_metadata"
                            )
                            or {},

                    }

                    activity(
                        "login",
                        "User logged in."
                    )

                    return redirect(
                        url_for(
                            "dashboard"
                        )
                    )

            except Exception:

                logger.exception(
                    "Login failed"
                )

                flash(
                    "Login failed. Check the Render logs.",
                    "error"
                )

    return page(

        "Login",

        """
<section class="card form">

<h1>
KOJA Login
</h1>

<form method="POST">

<label>
Email
</label>

<input
    type="email"
    name="email"
    required
    autocomplete="email"
>

<label>
Password
</label>

<input
    type="password"
    name="password"
    required
    autocomplete="current-password"
>

<br>

<button type="submit">
Login
</button>

</form>

<p class="muted">
No account?
<a href="/register">
Create Account
</a>
</p>

</section>
"""
    )


# ============================================================
# LOGOUT
# ============================================================

@app.route("/logout")
def logout():

    auth_logout()

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

    current = user()

    name = (
        current.get("full_name")
        or current.get("email")
        or "User"
    )

    return page(

        "Dashboard",

        f"""
<section class="hero">

<h1>
Welcome, {name}
</h1>

<p>
Your KOJA AFRICA dashboard.
</p>

</section>

<br>

<section class="grid">

<div class="service">

<h2>📚 Assignments</h2>

<p class="muted">
Submit assignments and
academic questions.
</p>

<a
    class="btn"
    href="/assignments"
>
Open
</a>

</div>

<div class="service">

<h2>🌾 Farmers</h2>

<p class="muted">
Register and manage
farmer services.
</p>

<a
    class="btn"
    href="/farmer"
>
Open
</a>

</div>

<div class="service">

<h2>🚚 Delivery</h2>

<p class="muted">
Drivers, GPS and delivery
requests.
</p>

<a
    class="btn"
    href="/driver"
>
Open
</a>

</div>

<div class="service">

<h2>📄 Documents</h2>

<p class="muted">
Browse KOJA documents.
</p>

<a
    class="btn"
    href="/documents"
>
Open
</a>

</div>

<div class="service">

<h2>🔔 Notifications</h2>

<p class="muted">
View your notifications.
</p>

<a
    class="btn"
    href="/notifications"
>
Open
</a>

</div>

<div class="service">

<h2>👤 Profile</h2>

<p class="muted">
View your account details.
</p>

<a
    class="btn"
    href="/profile"
>
Open
</a>

</div>

</section>
"""
    )


# ============================================================
# SERVICES
# ============================================================

@app.route("/services")
@login_required
def services():

    services_list = [

        (
            "📚",
            "Assignments",
            "Academic questions and assignments.",
            "assignments"
        ),

        (
            "🌾",
            "Farmer Services",
            "Farmer registration and services.",
            "farmer"
        ),

        (
            "🚚",
            "Driver & Delivery",
            "Drivers, GPS and delivery requests.",
            "driver"
        ),

        (
            "📄",
            "Documents",
            "Academic and service documents.",
            "documents"
        ),

        (
            "🎓",
            "University",
            "University and college services.",
            "university"
        ),

        (
            "💼",
            "CV & Jobs",
            "CV and job application services.",
            "cv"
        ),

        (
            "🧾",
            "TPIN",
            "TPIN-related services.",
            "tpin"
        ),

    ]

    cards = ""

    for icon, name, description, route_name in (
        services_list
    ):

        cards += f"""

<div class="service">

<h2>
{icon} {name}
</h2>

<p class="muted">
{description}
</p>

<a
    class="btn"
    href="/service/{route_name}"
>
Open
</a>

</div>

"""

    return page(
        "Services",
        f"""
<section class="card">

<h1>
KOJA Services
</h1>

<p class="muted">
Select the service you need.
</p>

</section>

<br>

<section class="grid">

{cards}

</section>
"""
    )


# ============================================================
# SERVICE ROUTER
# ============================================================

@app.route(
    "/service/<service_name>"
)
@login_required
def service_router(
    service_name
):

    routes = {

        "assignments":
            "assignments",

        "farmer":
            "farmer",

        "driver":
            "driver",

        "documents":
            "documents",

        "university":
            "university",

        "cv":
            "cv",

        "tpin":
            "tpin",

    }

    endpoint = routes.get(
        service_name
    )

    if endpoint:

        return redirect(
            url_for(endpoint)
        )

    flash(
        "Service not found.",
        "error"
    )

    return redirect(
        url_for("services")
    )


# ============================================================
# ASSIGNMENTS
# ============================================================

@app.route(
    "/assignments",
    methods=["GET", "POST"]
)
@login_required
def assignments():

    if request.method == "POST":

        question = (
            request.form.get(
                "question",
                ""
            ).strip()
        )

        subject = (
            request.form.get(
                "subject",
                ""
            ).strip()
        )

        if not question:

            flash(
                "Please enter your question.",
                "error"
            )

        else:

            uid = user_id()

            candidates = [

                {
                    "student_id": uid,
                    "student_name":
                        user().get(
                            "full_name"
                        )
                        or user().get(
                            "email"
                        ),
                    "question":
                        question,
                    "subject":
                        subject,
                    "status":
                        "pending",
                },

                {
                    "user_id": uid,
                    "question":
                        question,
                    "subject":
                        subject,
                    "status":
                        "pending",
                },

                {
                    "user_id": uid,
                    "question":
                        question,
                },

            ]

            result, error = (
                flexible_insert(
                    TABLE_QUESTIONS,
                    candidates
                )
            )

            if error:

                flash(
                    "Could not submit question: "
                    + error,
                    "error"
                )

            else:

                activity(
                    "question_created",
                    "Academic question submitted."
                )

                flash(
                    "Question submitted successfully.",
                    "success"
                )

                return redirect(
                    url_for(
                        "assignments"
                    )
                )

    return page(

        "Assignments",

        """
<section class="hero">

<h1>
📚 Academic Assignments
</h1>

<p>
Submit your academic question
to KOJA.
</p>

</section>

<br>

<section class="card form">

<h2>
Ask a Question
</h2>

<form method="POST">

<label>
Subject
</label>

<input
    type="text"
    name="subject"
    placeholder="e.g. Biology"
>

<label>
Question
</label>

<textarea
    name="question"
    required
    placeholder="Write your question here..."
></textarea>

<br>

<button type="submit">
Submit Question
</button>

</form>

</section>
"""
    )


# ============================================================
# DOCUMENTS
# ============================================================

@app.route("/documents")
@login_required
def documents():

    rows, error = db_select(

        TABLE_DOCUMENTS,

        params={
            "select":
                "*",
            "is_active":
                "eq.true",
            "order":
                "created_at.desc",
            "limit":
                "50",
        }

    )

    if error:

        rows = []

        flash(
            "Documents could not be loaded: "
            + error,
            "error"
        )

    return page(

        "Documents",

        render_template_string(

            """
<section class="card">

<h1>
📄 KOJA Document Library
</h1>

<p class="muted">
Available academic and service documents.
</p>

</section>

<br>

<section class="grid">

{% if rows %}

{% for row in rows %}

<div class="service">

<h3>
{{ row.get("title") or "Untitled Document" }}
</h3>

<p class="muted">
{{ row.get("description") or "" }}
</p>

<p>
<strong>
Subject:
</strong>

{{ row.get("subject") or "-" }}

</p>

{% if row.get("file_url") %}

<a
    class="btn"
    href="{{ row.get("file_url") }}"
    target="_blank"
>
Open Document
</a>

{% elif row.get("file_path") %}

<a
    class="btn"
    href="{{ url_for(
        'document_download',
        document_id=row.get('id')
    ) }}"
>
Open Document
</a>

{% endif %}

</div>

{% endfor %}

{% else %}

<div class="service">

<h3>
No documents yet
</h3>

<p class="muted">
Documents will appear here after
they are uploaded.
</p>

</div>

{% endif %}

</section>
""",

            rows=rows or []

        )

    )


# ============================================================
# DOCUMENT DOWNLOAD
# ============================================================

@app.route(
    "/documents/<document_id>/download"
)
@login_required
def document_download(
    document_id
):

    rows, error = db_select(

        TABLE_DOCUMENTS,

        params={
            "select":
                "*",
            "id":
                f"eq.{document_id}",
            "limit":
                "1",
        }

    )

    if error or not rows:

        flash(
            "Document not found.",
            "error"
        )

        return redirect(
            url_for("documents")
        )

    document = rows[0]

    file_url = document.get(
        "file_url"
    )

    if file_url:

        return redirect(
            file_url
        )

    file_path = document.get(
        "file_path"
    )

    if not file_path:

        flash(
            "Document file is unavailable.",
            "error"
        )

        return redirect(
            url_for("documents")
        )

    url = storage_url(
        f"{STORAGE_BUCKET}/{file_path}"
    )

    try:

        response = requests.get(

            url,

            headers={
                "Authorization":
                    f"Bearer "
                    f"{database_key()}",
                "apikey":
                    database_key(),
            },

            timeout=60
        )

        if response.status_code >= 400:

            flash(
                error_text(
                    response
                ),
                "error"
            )

            return redirect(
                url_for("documents")
            )

        filename = (
            document.get(
                "file_name"
            )
            or "document"
        )

        return send_file(

            io.BytesIO(
                response.content
            ),

            as_attachment=True,

            download_name=filename,

            mimetype=(
                document.get(
                    "mime_type"
                )
                or "application/octet-stream"
            )

        )

    except Exception:

        logger.exception(
            "Document download failed"
        )

        flash(
            "Document download failed.",
            "error"
        )

        return redirect(
            url_for("documents")
        )


# ============================================================
# FARMER
# ============================================================

@app.route(
    "/farmer",
    methods=["GET", "POST"]
)
@login_required
def farmer():

    if request.method == "POST":

        full_name = (
            request.form.get(
                "full_name",
                ""
            ).strip()
        )

        phone = (
            request.form.get(
                "phone",
                ""
            ).strip()
        )

        location = (
            request.form.get(
                "location",
                ""
            ).strip()
        )

        farming_type = (
            request.form.get(
                "farming_type",
                ""
            ).strip()
        )

        if not full_name or not phone:

            flash(
                "Name and phone are required.",
                "error"
            )

        else:

            uid = user_id()

            candidates = [

                {
                    "user_id": uid,
                    "full_name":
                        full_name,
                    "phone":
                        phone,
                    "location":
                        location,
                    "farming_type":
                        farming_type,
                    "status":
                        "pending",
                },

                {
                    "user_id": uid,
                    "full_name":
                        full_name,
                    "phone":
                        phone,
                    "location":
                        location,
                },

                {
                    "full_name":
                        full_name,
                    "phone":
                        phone,
                },

            ]

            result, error = (
                flexible_insert(
                    TABLE_FARMERS,
                    candidates
                )
            )

            if error:

                flash(
                    "Farmer registration failed: "
                    + error,
                    "error"
                )

            else:

                activity(
                    "farmer_registered",
                    "Farmer registration submitted."
                )

                flash(
                    "Farmer registration submitted successfully.",
                    "success"
                )

                return redirect(
                    url_for("farmer")
                )

    return page(

        "Farmer Services",

        """
<section class="hero">

<h1>
🌾 Farmer Registration
</h1>

<p>
Register for KOJA farmer services.
</p>

</section>

<br>

<section class="card form">

<form method="POST">

<label>
Full Name
</label>

<input
    type="text"
    name="full_name"
    required
>

<label>
Phone
</label>

<input
    type="tel"
    name="phone"
    required
>

<label>
Location
</label>

<input
    type="text"
    name="location"
>

<label>
Type of Farming
</label>

<input
    type="text"
    name="farming_type"
    placeholder="e.g. crops, livestock"
>

<br>

<button type="submit">
Register Farmer
</button>

</form>

</section>
"""
    )


# ============================================================
# DRIVER
# ============================================================

@app.route(
    "/driver",
    methods=["GET", "POST"]
)
@login_required
def driver():

    if request.method == "POST":

        full_name = (
            request.form.get(
                "full_name",
                ""
            ).strip()
        )

        phone = (
            request.form.get(
                "phone",
                ""
            ).strip()
        )

        vehicle_type = (
            request.form.get(
                "vehicle_type",
                ""
            ).strip()
        )

        vehicle_number = (
            request.form.get(
                "vehicle_number",
                ""
            ).strip()
        )

        license_number = (
            request.form.get(
                "license_number",
                ""
            ).strip()
        )

        if not full_name:

            flash(
                "Full name is required.",
                "error"
            )

        elif not phone:

            flash(
                "Phone is required.",
                "error"
            )

        else:

            uid = user_id()

            candidates = [

                {
                    "user_id": uid,
                    "full_name":
                        full_name,
                    "phone":
                        phone,
                    "email":
                        user().get(
                            "email"
                        ),
                    "vehicle_type":
                        vehicle_type,
                    "vehicle_number":
                        vehicle_number,
                    "license_number":
                        license_number,
                    "status":
                        "pending",
                    "is_online":
                        False,
                },

                {
                    "user_id": uid,
                    "full_name":
                        full_name,
                    "phone":
                        phone,
                    "vehicle_type":
                        vehicle_type,
                    "vehicle_number":
                        vehicle_number,
                    "license_number":
                        license_number,
                    "status":
                        "pending",
                    "is_online":
                        False,
                },

                {
                    "full_name":
                        full_name,
                    "phone":
                        phone,
                    "vehicle_type":
                        vehicle_type,
                    "vehicle_number":
                        vehicle_number,
                    "license_number":
                        license_number,
                },

            ]

            result, error = (
                flexible_insert(
                    TABLE_DRIVERS,
                    candidates
                )
            )

            if error:

                flash(
                    "Driver registration failed: "
                    + error,
                    "error"
                )

            else:

                activity(
                    "driver_registered",
                    "Driver registration submitted."
                )

                flash(
                    "Driver registration submitted successfully.",
                    "success"
                )

                return redirect(
                    url_for("driver")
                )

    return page(

        "Driver Registration",

        """
<section class="hero">

<h1>
🚚 Driver & Delivery
</h1>

<p>
Register as a KOJA delivery driver.
</p>

</section>

<br>

<section class="card form">

<form method="POST">

<label>
Full Name
</label>

<input
    type="text"
    name="full_name"
    required
>

<label>
Phone
</label>

<input
    type="tel"
    name="phone"
    required
>

<label>
Vehicle Type
</label>

<select
    name="vehicle_type"
>

<option value="">
Select vehicle
</option>

<option value="motorbike">
Motorbike
</option>

<option value="car">
Car
</option>

<option value="van">
Van
</option>

<option value="truck">
Truck
</option>

</select>

<label>
Vehicle Number
</label>

<input
    type="text"
    name="vehicle_number"
>

<label>
License Number
</label>

<input
    type="text"
    name="license_number"
>

<br>

<button type="submit">
Register as Driver
</button>

</form>

</section>

<br>

<section class="card">

<h2>
Driver GPS
</h2>

<p class="muted">
After driver approval, the driver can
go online and share their location so
customers can find nearby drivers.
</p>

<div class="actions">

<a
    class="btn"
    href="/driver/online"
>
Driver Online
</a>

<a
    class="btn"
    href="/driver/nearby"
>
Nearby Drivers
</a>

</div>

</section>
"""
    )


# ============================================================
# DRIVER ONLINE
# ============================================================

@app.route(
    "/driver/online",
    methods=["GET", "POST"]
)
@login_required
def driver_online():

    uid = user_id()

    if request.method == "POST":

        is_online = (
            request.form.get(
                "is_online"
            )
            == "true"
        )

        candidates = [

            {
                "is_online":
                    is_online
            }

        ]

        result, error = (
            db_update(

                TABLE_DRIVERS,

                {
                    "user_id":
                        f"eq.{uid}"
                },

                candidates[0]

            )
        )

        if error:

            flash(
                "Could not update driver status: "
                + error,
                "error"
            )

        else:

            flash(
                "Driver status updated.",
                "success"
            )

        return redirect(
            url_for(
                "driver_online"
            )
        )

    drivers, error = db_select(

        TABLE_DRIVERS,

        params={
            "select":
                "*",
            "user_id":
                f"eq.{uid}",
            "limit":
                "1",
        }

    )

    driver_record = (
        drivers[0]
        if drivers
        else {}
    )

    online = bool(
        driver_record.get(
            "is_online",
            False
        )
    )

    return page(

        "Driver Online",

        f"""
<section class="card">

<h1>
Driver Online Status
</h1>

<p>

Current status:

<span class="badge">

{"ONLINE" if online else "OFFLINE"}

</span>

</p>

<form method="POST">

<input
    type="hidden"
    name="is_online"
    value="{"false" if online else "true"}"
>

<button type="submit">

{"Go Offline" if online else "Go Online"}

</button>

</form>

</section>

<br>

<section class="card">

<h2>
GPS Location
</h2>

<p class="muted">
Use the location endpoint to send the
driver's current latitude and longitude.
</p>

</section>
"""
    )


# ============================================================
# DRIVER GPS API
# ============================================================

@app.route(
    "/api/driver/location",
    methods=["POST"]
)
@login_required
def driver_location():

    uid = user_id()

    data = request.get_json(
        silent=True
    ) or {}

    latitude = data.get(
        "latitude"
    )

    longitude = data.get(
        "longitude"
    )

    accuracy = data.get(
        "accuracy"
    )

    if latitude is None or longitude is None:

        return jsonify({

            "success":
                False,

            "message":
                "Latitude and longitude are required."

        }), 400

    candidates = [

        {
            "driver_id":
                uid,
            "user_id":
                uid,
            "latitude":
                latitude,
            "longitude":
                longitude,
            "accuracy":
                accuracy,
            "updated_at":
                utc_now(),
        },

        {
            "driver_id":
                uid,
            "latitude":
                latitude,
            "longitude":
                longitude,
        },

        {
            "user_id":
                uid,
            "latitude":
                latitude,
            "longitude":
                longitude,
        },

    ]

    result, error = (
        flexible_insert(
            TABLE_DRIVER_LOCATIONS,
            candidates
        )
    )

    if error:

        return jsonify({

            "success":
                False,

            "message":
                error

        }), 400

    return jsonify({

        "success":
            True,

        "message":
            "Location updated."

    })


# ============================================================
# NEARBY DRIVERS
# ============================================================

@app.route(
    "/driver/nearby"
)
@login_required
def nearby_drivers():

    rows, error = db_select(

        TABLE_DRIVERS,

        params={
            "select":
                "*",
            "is_online":
                "eq.true",
            "status":
                "eq.approved",
            "limit":
                "50",
        }

    )

    if error:

        rows = []

        flash(
            "Nearby drivers could not be loaded: "
            + error,
            "error"
        )

    return page(

        "Nearby Drivers",

        render_template_string(

            """
<section class="hero">

<h1>
🚚 Nearby Drivers
</h1>

<p>
Drivers currently available for
delivery requests.
</p>

</section>

<br>

<section class="grid">

{% if rows %}

{% for driver in rows %}

<div class="service">

<h2>
🚚
</h2>

<h3>
{{ driver.get("full_name") or "Driver" }}
</h3>

<p>
Vehicle:
{{ driver.get("vehicle_type") or "-" }}
</p>

<p>
Vehicle No:
{{ driver.get("vehicle_number") or "-" }}
</p>

<span class="badge">
ONLINE
</span>

<br><br>

<a
    class="btn"
    href="{{ url_for(
        'request_delivery',
        driver_id=driver.get('id')
    ) }}"
>
Request Delivery
</a>

</div>

{% endfor %}

{% else %}

<div class="service">

<h3>
No approved drivers online
</h3>

<p class="muted">
Nearby available drivers will
appear here.
</p>

</div>

{% endif %}

</section>
""",

            rows=rows or []

        )

    )


# ============================================================
# DELIVERY REQUEST
# ============================================================

@app.route(
    "/delivery/request/<driver_id>",
    methods=["GET", "POST"]
)
@login_required
def request_delivery(
    driver_id
):

    if request.method == "POST":

        pickup = (
            request.form.get(
                "pickup",
                ""
            ).strip()
        )

        destination = (
            request.form.get(
                "destination",
                ""
            ).strip()
        )

        notes = (
            request.form.get(
                "notes",
                ""
            ).strip()
        )

        if not pickup or not destination:

            flash(
                "Pickup and destination are required.",
                "error"
            )

        else:

            uid = user_id()

            candidates = [

                {
                    "customer_id":
                        uid,
                    "user_id":
                        uid,
                    "driver_id":
                        driver_id,
                    "pickup_location":
                        pickup,
                    "destination":
                        destination,
                    "notes":
                        notes,
                    "status":
                        "pending",
                },

                {
                    "user_id":
                        uid,
                    "driver_id":
                        driver_id,
                    "pickup":
                        pickup,
                    "destination":
                        destination,
                    "notes":
                        notes,
                    "status":
                        "pending",
                },

            ]

            result, error = (
                flexible_insert(
                    TABLE_DELIVERY_REQUESTS,
                    candidates
                )
            )

            if error:

                flash(
                    "Delivery request failed: "
                    + error,
                    "error"
                )

            else:

                activity(
                    "delivery_requested",
                    "Delivery request submitted."
                )

                flash(
                    "Delivery request sent.",
                    "success"
                )

                return redirect(
                    url_for(
                        "delivery_requests"
                    )
                )

    return page(

        "Request Delivery",

        f"""
<section class="card form">

<h1>
Request Delivery
</h1>

<form method="POST">

<label>
Pickup Location
</label>

<input
    type="text"
    name="pickup"
    required
    placeholder="Where should the driver collect?"
>

<label>
Destination
</label>

<input
    type="text"
    name="destination"
    required
    placeholder="Where should the driver deliver?"
>

<label>
Notes
</label>

<textarea
    name="notes"
    placeholder="Additional instructions"
></textarea>

<br>

<button type="submit">
Send Delivery Request
</button>

</form>

</section>
"""
    )


# ============================================================
# DELIVERY REQUESTS
# ============================================================

@app.route(
    "/delivery/requests"
)
@login_required
def delivery_requests():

    uid = user_id()

    rows, error = db_select(

        TABLE_DELIVERY_REQUESTS,

        params={
            "select":
                "*",
            "user_id":
                f"eq.{uid}",
            "order":
                "created_at.desc",
            "limit":
                "50",
        }

    )

    if error:

        rows = []

    return page(

        "Delivery Requests",

        render_template_string(

            """
<section class="card">

<h1>
🚚 My Delivery Requests
</h1>

</section>

<br>

<section class="grid">

{% for row in rows %}

<div class="service">

<h3>
Delivery
</h3>

<p>
Pickup:
{{ row.get("pickup_location")
   or row.get("pickup")
   or "-" }}
</p>

<p>
Destination:
{{ row.get("destination")
   or "-" }}
</p>

<p>
Status:
<strong>
{{ row.get("status") or "pending" }}
</strong>
</p>

</div>

{% else %}

<div class="service">

<h3>
No delivery requests
</h3>

</div>

{% endfor %}

</section>
""",

            rows=rows or []

        )

    )


# ============================================================
# NOTIFICATIONS
# ============================================================

@app.route(
    "/notifications"
)
@login_required
def notifications():

    uid = user_id()

    rows, error = db_select(

        TABLE_NOTIFICATIONS,

        params={
            "select":
                "*",
            "user_id":
                f"eq.{uid}",
            "order":
                "created_at.desc",
            "limit":
                "50",
        }

    )

    if error:

        rows = []

    return page(

        "Notifications",

        render_template_string(

            """
<section class="card">

<h1>
🔔 Notifications
</h1>

</section>

<br>

<section class="grid">

{% for row in rows %}

<div class="service">

<h3>
{{ row.get("title")
   or "Notification" }}
</h3>

<p>
{{ row.get("message")
   or row.get("description")
   or "" }}
</p>

<p class="muted">
{{ row.get("created_at")
   or "" }}
</p>

</div>

{% else %}

<div class="service">

<h3>
No notifications
</h3>

<p class="muted">
Your notifications will appear here.
</p>

</div>

{% endfor %}

</section>
""",

            rows=rows or []

        )

    )


# ============================================================
# PROFILE
# ============================================================

@app.route("/profile")
@login_required
def profile():

    current = user()

    return page(

        "Profile",

        f"""
<section class="card">

<h1>
👤 My Profile
</h1>

<p>
<strong>
Name:
</strong>

{current.get(
    "full_name",
    ""
)}

</p>

<p>
<strong>
Email:
</strong>

{current.get(
    "email",
    ""
)}

</p>

<p>
<strong>
User ID:
</strong>

{current.get(
    "id",
    ""
)}

</p>

</section>
"""
    )


# ============================================================
# API CURRENT USER
# ============================================================

@app.route("/api/me")
@login_required
def api_me():

    return jsonify({

        "success":
            True,

        "user":
            user(),

    })


# ============================================================
# API SERVICES
# ============================================================

@app.route("/api/services")
@login_required
def api_services():

    return jsonify({

        "success":
            True,

        "services": [

            {
                "id":
                    "assignments",
                "name":
                    "Assignments"
            },

            {
                "id":
                    "farmer",
                "name":
                    "Farmer Services"
            },

            {
                "id":
                    "driver",
                "name":
                    "Driver & Delivery"
            },

            {
                "id":
                    "documents",
                "name":
                    "Documents"
            },

        ]

    })


# ============================================================
# API SYSTEM
# ============================================================

@app.route("/api/system")
def api_system():

    return jsonify({

        "application":
            APP_NAME,

        "version":
            "koja-full-v1",

        "flask":
            True,

        "supabase":
            configured(),

        "authentication":
            "Supabase Auth",

        "database":
            "Supabase REST",

        "storage":
            STORAGE_BUCKET,

    })


# ============================================================
# ADMIN DASHBOARD
# ============================================================

@app.route("/admin")
@admin_required
def admin_dashboard():

    counts = {}

    tables = [

        "profiles",
        "questions",
        "documents",
        "farmers",
        "drivers",
        "delivery_requests",
        "notifications",

    ]

    for table in tables:

        rows, error = db_select(

            table,

            params={
                "select":
                    "id",
                "limit":
                    "1000",
            }

        )

        if isinstance(rows, list):

            counts[table] = len(rows)

        else:

            counts[table] = 0

    return page(

        "Admin Dashboard",

        f"""
<section class="hero">

<h1>
Admin Dashboard
</h1>

<p>
KOJA AFRICA administration.
</p>

</section>

<br>

<section class="grid">

<div class="stat">
<div class="stat-number">
{counts.get("profiles", 0)}
</div>
Profiles
</div>

<div class="stat">
<div class="stat-number">
{counts.get("questions", 0)}
</div>
Questions
</div>

<div class="stat">
<div class="stat-number">
{counts.get("documents", 0)}
</div>
Documents
</div>

<div class="stat">
<div class="stat-number">
{counts.get("farmers", 0)}
</div>
Farmers
</div>

<div class="stat">
<div class="stat-number">
{counts.get("drivers", 0)}
</div>
Drivers
</div>

<div class="stat">
<div class="stat-number">
{counts.get("delivery_requests", 0)}
</div>
Deliveries
</div>

</section>

<br>

<section class="card">

<h2>
Administration
</h2>

<div class="actions">

<a
    class="btn"
    href="/admin/drivers"
>
Drivers
</a>

<a
    class="btn"
    href="/admin/questions"
>
Questions
</a>

<a
    class="btn"
    href="/admin/farmers"
>
Farmers
</a>

</div>

</section>
"""
    )


# ============================================================
# ADMIN DRIVERS
# ============================================================

@app.route(
    "/admin/drivers"
)
@admin_required
def admin_drivers():

    rows, error = db_select(

        TABLE_DRIVERS,

        params={
            "select":
                "*",
            "order":
                "created_at.desc",
            "limit":
                "100",
        }

    )

    if error:

        rows = []

    return page(

        "Admin Drivers",

        render_template_string(

            """
<section class="card">

<h1>
Driver Management
</h1>

<div class="table-wrap">

<table>

<thead>

<tr>
<th>Name</th>
<th>Phone</th>
<th>Vehicle</th>
<th>Status</th>
<th>Online</th>
</tr>

</thead>

<tbody>

{% for row in rows %}

<tr>

<td>
{{ row.get("full_name") or "-" }}
</td>

<td>
{{ row.get("phone") or "-" }}
</td>

<td>
{{ row.get("vehicle_type") or "-" }}
</td>

<td>
{{ row.get("status") or "-" }}
</td>

<td>
{{ row.get("is_online") }}
</td>

</tr>

{% endfor %}

</tbody>

</table>

</div>

</section>
""",

            rows=rows or []

        )

    )


# ============================================================
# ADMIN QUESTIONS
# ============================================================

@app.route(
    "/admin/questions"
)
@admin_required
def admin_questions():

    rows, error = db_select(

        TABLE_QUESTIONS,

        params={
            "select":
                "*",
            "order":
                "created_at.desc",
            "limit":
                "100",
        }

    )

    if error:

        rows = []

    return page(

        "Admin Questions",

        render_template_string(

            """
<section class="card">

<h1>
Academic Questions
</h1>

<div class="table-wrap">

<table>

<thead>

<tr>
<th>Subject</th>
<th>Question</th>
<th>Status</th>
<th>Created</th>
</tr>

</thead>

<tbody>

{% for row in rows %}

<tr>

<td>
{{ row.get("subject") or "-" }}
</td>

<td>
{{ row.get("question") or "-" }}
</td>

<td>
{{ row.get("status") or "-" }}
</td>

<td>
{{ row.get("created_at") or "-" }}
</td>

</tr>

{% endfor %}

</tbody>

</table>

</div>

</section>
""",

            rows=rows or []

        )

    )


# ============================================================
# ADMIN FARMERS
# ============================================================

@app.route(
    "/admin/farmers"
)
@admin_required
def admin_farmers():

    rows, error = db_select(

        TABLE_FARMERS,

        params={
            "select":
                "*",
            "order":
                "created_at.desc",
            "limit":
                "100",
        }

    )

    if error:

        rows = []

    return page(

        "Admin Farmers",

        render_template_string(

            """
<section class="card">

<h1>
Farmer Registrations
</h1>

<div class="table-wrap">

<table>

<thead>

<tr>
<th>Name</th>
<th>Phone</th>
<th>Location</th>
<th>Status</th>
</tr>

</thead>

<tbody>

{% for row in rows %}

<tr>

<td>
{{ row.get("full_name") or "-" }}
</td>

<td>
{{ row.get("phone") or "-" }}
</td>

<td>
{{ row.get("location") or "-" }}
</td>

<td>
{{ row.get("status") or "-" }}
</td>

</tr>

{% endfor %}

</tbody>

</table>

</div>

</section>
""",

            rows=rows or []

        )

    )


# ============================================================
# UNIVERSITY
# ============================================================

@app.route("/university")
@login_required
def university():

    return page(

        "University Services",

        """
<section class="card">

<h1>
🎓 University Services
</h1>

<p class="muted">
University and college services
will be connected to the relevant
KOJA tables.
</p>

</section>
"""
    )


# ============================================================
# CV
# ============================================================

@app.route("/cv")
@login_required
def cv():

    return page(

        "CV & Jobs",

        """
<section class="card">

<h1>
💼 CV & Jobs
</h1>

<p class="muted">
CV creation and job application
services.
</p>

</section>
"""
    )


# ============================================================
# TPIN
# ============================================================

@app.route("/tpin")
@login_required
def tpin():

    return page(

        "TPIN Services",

        """
<section class="card">

<h1>
🧾 TPIN Services
</h1>

<p class="muted">
TPIN-related services will be
connected here.
</p>

</section>
"""
    )


# ============================================================
# 404
# ============================================================

@app.errorhandler(404)
def error_404(error):

    return page(

        "Not Found",

        """
<section class="card">

<h1>
404
</h1>

<p>
The page does not exist.
</p>

<a
    class="btn"
    href="/"
>
Home
</a>

</section>
"""
    ), 404


# ============================================================
# 413
# ============================================================

@app.errorhandler(413)
def error_413(error):

    return page(

        "File Too Large",

        """
<section class="card">

<h1>
File Too Large
</h1>

<p>
The maximum upload size is 15 MB.
</p>

</section>
"""
    ), 413


# ============================================================
# 500
# ============================================================

@app.errorhandler(500)
def error_500(error):

    logger.exception(
        "Unhandled application error"
    )

    return page(

        "Server Error",

        """
<section class="card">

<h1>
Server Error
</h1>

<p>
KOJA encountered an unexpected
server error.
</p>

<p class="muted">
Check the Render logs for the
exact traceback.
</p>

</section>
"""
    ), 500


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    port = int(
        os.getenv(
            "PORT",
            "5000"
        )
    )

    app.run(

        host="0.0.0.0",

        port=port,

        debug=False

    )

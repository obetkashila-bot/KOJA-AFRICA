import os
import uuid
import html
import logging
from io import BytesIO
from datetime import datetime, timezone
from functools import wraps

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
    jsonify,
    send_file
)
from werkzeug.utils import secure_filename

load_dotenv()

# ============================================================
# KOJA AFRICA
# THREE SERVICES ONLY
#
# 1. ASSIGNMENTS
# 2. DRIVER & DELIVERY
# 3. CV GENERATOR
#
# Features:
# - Email/password authentication
# - Assignment submission
# - Assignment answers
# - Driver registration
# - Driver approval
# - Driver online/offline status
# - Driver GPS tracking
# - Live driver map
# - Delivery requests
# - Driver assignment
# - Customer delivery tracking
# - Admin delivery management
# - CV self-generation
# - Admin CV generation
# - PDF CV generation
# - Responsive mobile interface
# - Animated interface
# - No emojis
# ============================================================

app = Flask(__name__)

app.secret_key = os.getenv(
    "FLASK_SECRET_KEY",
    "CHANGE_THIS_SECRET_KEY"
)

SUPABASE_URL = os.getenv(
    "SUPABASE_URL",
    ""
).rstrip("/")

SUPABASE_SERVICE_KEY = os.getenv(
    "SUPABASE_SERVICE_KEY",
    ""
)

SUPABASE_BUCKET = os.getenv(
    "SUPABASE_BUCKET",
    "koja-files"
)

ADMIN_EMAIL = os.getenv(
    "ADMIN_EMAIL",
    ""
).strip().lower()

MAX_FILE_SIZE = 15 * 1024 * 1024

ALLOWED_EXTENSIONS = {
    "pdf",
    "doc",
    "docx",
    "jpg",
    "jpeg",
    "png",
    "webp"
}

logging.basicConfig(
    level=logging.INFO
)

logger = logging.getLogger("koja-africa")


# ============================================================
# OPTIONAL REPORTLAB
# ============================================================

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_LEFT, TA_CENTER
    from reportlab.platypus import (
        SimpleDocTemplate,
        Paragraph,
        Spacer,
        Table,
        TableStyle,
        HRFlowable
    )
    REPORTLAB_AVAILABLE = True
except Exception:
    REPORTLAB_AVAILABLE = False


# ============================================================
# BASIC HELPERS
# ============================================================

def configuration_ok():
    return bool(
        SUPABASE_URL and
        SUPABASE_SERVICE_KEY
    )


def now_iso():
    return datetime.now(
        timezone.utc
    ).isoformat()


def safe(value):
    if value is None:
        return ""

    return html.escape(
        str(value),
        quote=True
    )


def allowed_file(filename):
    if not filename or "." not in filename:
        return False

    extension = filename.rsplit(
        ".",
        1
    )[1].lower()

    return extension in ALLOWED_EXTENSIONS


def current_user():
    return session.get("user")


def logged_in():
    return bool(
        current_user()
    )


def is_admin():
    u = current_user()

    if not u:
        return False

    email = (
        u.get("email", "")
        .strip()
        .lower()
    )

    return bool(
        ADMIN_EMAIL and
        email == ADMIN_EMAIL
    )


# ============================================================
# SUPABASE HEADERS
# ============================================================

def api_headers(prefer=None):
    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization":
            f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type":
            "application/json"
    }

    if prefer:
        headers["Prefer"] = prefer

    return headers


# ============================================================
# SUPABASE DATABASE
# ============================================================

def db_get(table, params=None):
    if not configuration_ok():
        return None, "Supabase is not configured."

    try:
        response = requests.get(
            f"{SUPABASE_URL}/rest/v1/{table}",
            headers=api_headers(),
            params=params or {},
            timeout=30
        )

        if not response.ok:
            logger.error(
                "Supabase GET %s: %s",
                table,
                response.text
            )
            return None, response.text

        try:
            return response.json(), None
        except Exception:
            return [], None

    except Exception as exc:
        logger.exception(
            "Supabase GET error"
        )
        return None, str(exc)


def db_insert(table, data):
    if not configuration_ok():
        return None, "Supabase is not configured."

    try:
        response = requests.post(
            f"{SUPABASE_URL}/rest/v1/{table}",
            headers=api_headers(
                "return=representation"
            ),
            json=data,
            timeout=30
        )

        if not response.ok:
            logger.error(
                "Supabase INSERT %s: %s",
                table,
                response.text
            )
            return None, response.text

        try:
            return response.json(), None
        except Exception:
            return [], None

    except Exception as exc:
        logger.exception(
            "Supabase INSERT error"
        )
        return None, str(exc)


def db_update(table, filters, data):
    if not configuration_ok():
        return None, "Supabase is not configured."

    params = {}

    for key, value in filters.items():
        params[key] = f"eq.{value}"

    try:
        response = requests.patch(
            f"{SUPABASE_URL}/rest/v1/{table}",
            headers=api_headers(
                "return=representation"
            ),
            params=params,
            json=data,
            timeout=30
        )

        if not response.ok:
            logger.error(
                "Supabase UPDATE %s: %s",
                table,
                response.text
            )
            return None, response.text

        try:
            return response.json(), None
        except Exception:
            return [], None

    except Exception as exc:
        logger.exception(
            "Supabase UPDATE error"
        )
        return None, str(exc)


# ============================================================
# AUTHENTICATION
# ============================================================

def auth_signup(email, password):
    try:
        response = requests.post(
            f"{SUPABASE_URL}/auth/v1/signup",
            headers={
                "apikey":
                    SUPABASE_SERVICE_KEY,
                "Content-Type":
                    "application/json"
            },
            json={
                "email": email,
                "password": password
            },
            timeout=30
        )

        if not response.ok:
            logger.error(
                "SIGNUP: %s",
                response.text
            )
            return None, response.text

        return response.json(), None

    except Exception as exc:
        logger.exception(
            "Signup error"
        )
        return None, str(exc)


def auth_login(email, password):
    try:
        response = requests.post(
            f"{SUPABASE_URL}/auth/v1/token"
            "?grant_type=password",
            headers={
                "apikey":
                    SUPABASE_SERVICE_KEY,
                "Content-Type":
                    "application/json"
            },
            json={
                "email": email,
                "password": password
            },
            timeout=30
        )

        if not response.ok:
            logger.error(
                "LOGIN: %s",
                response.text
            )
            return None, response.text

        return response.json(), None

    except Exception as exc:
        logger.exception(
            "Login error"
        )
        return None, str(exc)


# ============================================================
# STORAGE
# ============================================================

def storage_upload(file_storage, folder):
    if not file_storage:
        return None, "No file supplied."

    filename = secure_filename(
        file_storage.filename or ""
    )

    if not allowed_file(filename):
        return None, "Unsupported file type."

    file_storage.seek(0)

    content = file_storage.read()

    if len(content) > MAX_FILE_SIZE:
        return None, "File is larger than 15 MB."

    extension = filename.rsplit(
        ".",
        1
    )[1].lower()

    object_name = (
        f"{folder}/"
        f"{uuid.uuid4().hex}."
        f"{extension}"
    )

    content_type = (
        file_storage.mimetype
        or
        "application/octet-stream"
    )

    headers = {
        "apikey":
            SUPABASE_SERVICE_KEY,
        "Authorization":
            f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type":
            content_type,
        "x-upsert":
            "false"
    }

    try:
        response = requests.post(
            f"{SUPABASE_URL}/storage/v1/object/"
            f"{SUPABASE_BUCKET}/"
            f"{object_name}",
            headers=headers,
            data=content,
            timeout=60
        )

        if not response.ok:
            logger.error(
                "STORAGE UPLOAD: %s",
                response.text
            )
            return None, response.text

        return {
            "path": object_name,
            "filename": filename,
            "content_type": content_type,
            "size": len(content)
        }, None

    except Exception as exc:
        logger.exception(
            "Storage upload error"
        )
        return None, str(exc)


def storage_download(path):
    headers = {
        "apikey":
            SUPABASE_SERVICE_KEY,
        "Authorization":
            f"Bearer {SUPABASE_SERVICE_KEY}"
    }

    try:
        response = requests.get(
            f"{SUPABASE_URL}/storage/v1/object/"
            f"{SUPABASE_BUCKET}/{path}",
            headers=headers,
            timeout=60
        )

        if not response.ok:
            return None, response.text

        return response.content, None

    except Exception as exc:
        logger.exception(
            "Storage download error"
        )
        return None, str(exc)


# ============================================================
# DECORATORS
# ============================================================

def login_required(fn):

    @wraps(fn)
    def wrapper(*args, **kwargs):

        if not logged_in():
            flash(
                "Please login first."
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

        if not logged_in():
            return redirect(
                url_for("login")
            )

        if not is_admin():
            flash(
                "Administrator access required."
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
# MAIN HTML
# ============================================================

PAGE = """
<!DOCTYPE html>
<html lang="en">

<head>

<meta charset="UTF-8">

<meta name="viewport"
      content="width=device-width,
      initial-scale=1.0">

<meta name="theme-color"
      content="#0f172a">

<title>
{{ title }} - KOJA AFRICA
</title>

<link rel="stylesheet"
      href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">

<style>

*{
    box-sizing:border-box;
}

html{
    scroll-behavior:smooth;
}

body{
    margin:0;
    background:#f5f7fb;
    color:#172033;
    font-family:
        Inter,
        Arial,
        Helvetica,
        sans-serif;
    min-height:100vh;
}

/* =========================================================
   NAVIGATION
   ========================================================= */

.navbar{
    position:sticky;
    top:0;
    z-index:1000;
    background:
        rgba(15,23,42,.96);
    backdrop-filter:
        blur(12px);
    color:white;
    padding:14px 18px;
    box-shadow:
        0 5px 25px rgba(0,0,0,.15);
}

.nav-inner{
    max-width:1180px;
    margin:auto;
    display:flex;
    align-items:center;
    justify-content:space-between;
    gap:15px;
}

.brand{
    color:white;
    text-decoration:none;
    font-size:22px;
    font-weight:800;
    letter-spacing:.5px;
}

.nav-links{
    display:flex;
    flex-wrap:wrap;
    justify-content:flex-end;
    gap:5px;
}

.nav-links a{
    color:#e5e7eb;
    text-decoration:none;
    padding:9px 11px;
    border-radius:8px;
    font-size:14px;
    transition:
        background .2s ease,
        color .2s ease,
        transform .2s ease;
}

.nav-links a:hover{
    background:#1e293b;
    color:white;
    transform:translateY(-1px);
}

/* =========================================================
   PAGE
   ========================================================= */

.container{
    width:min(1180px, 100%);
    margin:auto;
    padding:25px 18px 50px;
}

.hero{
    position:relative;
    overflow:hidden;
    background:
        linear-gradient(
            135deg,
            #0f172a,
            #1d4ed8
        );
    color:white;
    padding:42px 30px;
    border-radius:22px;
    margin-bottom:24px;
    box-shadow:
        0 18px 50px rgba(15,23,42,.18);
    animation:
        heroIn .7s ease both;
}

.hero:before{
    content:"";
    position:absolute;
    width:220px;
    height:220px;
    border:1px solid
        rgba(255,255,255,.12);
    border-radius:50%;
    right:-80px;
    top:-90px;
    animation:
        floatCircle 6s ease-in-out infinite;
}

.hero:after{
    content:"";
    position:absolute;
    width:130px;
    height:130px;
    border:1px solid
        rgba(255,255,255,.08);
    border-radius:50%;
    left:-50px;
    bottom:-70px;
    animation:
        floatCircle 8s ease-in-out infinite reverse;
}

.hero-content{
    position:relative;
    z-index:2;
}

.hero h1{
    margin:0 0 10px;
    font-size:
        clamp(30px, 6vw, 52px);
}

.hero p{
    max-width:720px;
    line-height:1.7;
    color:#dbeafe;
}

/* =========================================================
   SERVICE CARDS
   ========================================================= */

.grid{
    display:grid;
    grid-template-columns:
        repeat(
            auto-fit,
            minmax(260px,1fr)
        );
    gap:18px;
}

.card{
    background:white;
    border-radius:17px;
    padding:21px;
    margin-bottom:18px;
    box-shadow:
        0 7px 25px
        rgba(15,23,42,.07);
    border:1px solid
        rgba(148,163,184,.16);
    animation:
        cardIn .55s ease both;
    transition:
        transform .25s ease,
        box-shadow .25s ease;
}

.card:hover{
    transform:
        translateY(-4px);
    box-shadow:
        0 15px 35px
        rgba(15,23,42,.11);
}

.service-card{
    min-height:250px;
    display:flex;
    flex-direction:column;
    justify-content:space-between;
}

.service-number{
    display:inline-flex;
    width:38px;
    height:38px;
    align-items:center;
    justify-content:center;
    background:#eff6ff;
    color:#1d4ed8;
    border-radius:10px;
    font-weight:800;
    margin-bottom:14px;
}

/* =========================================================
   FORMS
   ========================================================= */

label{
    display:block;
    font-size:14px;
    font-weight:700;
    margin:8px 0 5px;
}

input,
textarea,
select{
    width:100%;
    padding:12px 13px;
    margin:3px 0 12px;
    border:
        1px solid #d1d5db;
    border-radius:10px;
    background:white;
    color:#172033;
    font-size:15px;
    outline:none;
    transition:
        border .2s ease,
        box-shadow .2s ease;
}

input:focus,
textarea:focus,
select:focus{
    border-color:#2563eb;
    box-shadow:
        0 0 0 3px
        rgba(37,99,235,.1);
}

textarea{
    min-height:130px;
    resize:vertical;
}

/* =========================================================
   BUTTONS
   ========================================================= */

button,
.btn{
    border:0;
    border-radius:10px;
    padding:11px 17px;
    background:#2563eb;
    color:white;
    text-decoration:none;
    cursor:pointer;
    display:inline-block;
    font-size:14px;
    font-weight:700;
    transition:
        transform .2s ease,
        box-shadow .2s ease,
        opacity .2s ease;
}

button:hover,
.btn:hover{
    transform:
        translateY(-2px);
    box-shadow:
        0 8px 20px
        rgba(37,99,235,.2);
}

button:active,
.btn:active{
    transform:
        translateY(0);
}

.btn-dark{
    background:#111827;
}

.btn-green{
    background:#059669;
}

.btn-orange{
    background:#d97706;
}

.btn-red{
    background:#dc2626;
}

.btn-light{
    background:#e5e7eb;
    color:#111827;
}

/* =========================================================
   STATUS
   ========================================================= */

.status{
    display:inline-block;
    padding:5px 10px;
    border-radius:20px;
    background:#e5e7eb;
    color:#374151;
    font-size:12px;
    font-weight:700;
}

.status-online{
    background:#dcfce7;
    color:#166534;
}

.status-pending{
    background:#fef3c7;
    color:#92400e;
}

.status-completed{
    background:#dcfce7;
    color:#166534;
}

.status-cancelled{
    background:#fee2e2;
    color:#991b1b;
}

.location-live{
    color:#047857;
    font-weight:800;
}

/* =========================================================
   MAP
   ========================================================= */

.map{
    width:100%;
    height:420px;
    border-radius:17px;
    overflow:hidden;
    margin-top:15px;
    box-shadow:
        0 8px 25px
        rgba(15,23,42,.12);
}

.map-small{
    height:300px;
}

.map-status{
    display:flex;
    align-items:center;
    gap:8px;
    margin:10px 0;
    font-size:14px;
}

.live-dot{
    width:10px;
    height:10px;
    border-radius:50%;
    background:#16a34a;
    box-shadow:
        0 0 0 0
        rgba(22,163,74,.6);
    animation:
        pulse 1.7s infinite;
}

/* =========================================================
   ALERT
   ========================================================= */

.flash{
    background:#fff7ed;
    border:
        1px solid #fed7aa;
    color:#9a3412;
    padding:13px 15px;
    border-radius:10px;
    margin-bottom:12px;
    animation:
        slideDown .4s ease both;
}

/* =========================================================
   CV
   ========================================================= */

.cv-section{
    border-top:
        1px solid #e5e7eb;
    padding-top:18px;
    margin-top:20px;
}

.section-title{
    font-size:17px;
    font-weight:800;
    margin-bottom:12px;
}

/* =========================================================
   FOOTER
   ========================================================= */

footer{
    text-align:center;
    padding:35px 18px;
    color:#64748b;
    border-top:
        1px solid #e5e7eb;
    background:#fff;
}

footer strong{
    color:#172033;
}

/* =========================================================
   ANIMATIONS
   ========================================================= */

@keyframes heroIn{
    from{
        opacity:0;
        transform:
            translateY(18px);
    }
    to{
        opacity:1;
        transform:
            translateY(0);
    }
}

@keyframes cardIn{
    from{
        opacity:0;
        transform:
            translateY(15px);
    }
    to{
        opacity:1;
        transform:
            translateY(0);
    }
}

@keyframes slideDown{
    from{
        opacity:0;
        transform:
            translateY(-10px);
    }
    to{
        opacity:1;
        transform:
            translateY(0);
    }
}

@keyframes floatCircle{
    0%,100%{
        transform:
            translate(0,0);
    }
    50%{
        transform:
            translate(15px,12px);
    }
}

@keyframes pulse{
    0%{
        box-shadow:
            0 0 0 0
            rgba(22,163,74,.6);
    }
    70%{
        box-shadow:
            0 0 0 10px
            rgba(22,163,74,0);
    }
    100%{
        box-shadow:
            0 0 0 0
            rgba(22,163,74,0);
    }
}

/* =========================================================
   MOBILE
   ========================================================= */

@media(max-width:720px){

    .navbar{
        position:relative;
    }

    .nav-inner{
        display:block;
    }

    .brand{
        display:block;
        margin-bottom:10px;
    }

    .nav-links{
        justify-content:flex-start;
    }

    .nav-links a{
        padding:7px 8px;
        font-size:13px;
    }

    .container{
        padding:
            16px 12px 35px;
    }

    .hero{
        padding:30px 21px;
        border-radius:17px;
    }

    .card{
        padding:17px;
    }

    .map{
        height:350px;
    }

}

</style>

</head>

<body>

<nav class="navbar">

<div class="nav-inner">

<a class="brand"
   href="/">
   KOJA AFRICA
</a>

<div class="nav-links">

<a href="/">Home</a>

{% if session.get("user") %}

<a href="/dashboard">Dashboard</a>

<a href="/assignments">Assignments</a>

<a href="/drivers">Drivers</a>

<a href="/deliveries">
Deliveries
</a>

<a href="/cv">
CV
</a>

{% if is_admin_user %}

<a href="/admin">
Admin
</a>

{% endif %}

<a href="/logout">
Logout
</a>

{% else %}

<a href="/login">
Login
</a>

<a href="/register">
Create Account
</a>

{% endif %}

</div>

</div>

</nav>

<main class="container">

{% with messages =
get_flashed_messages() %}

{% for message in messages %}

<div class="flash">
{{ message }}
</div>

{% endfor %}

{% endwith %}

{{ content|safe }}

</main>

<footer>

<strong>KOJA AFRICA</strong>

<br>

Assignments |
Driver & Delivery |
CV Generation

</footer>

<script
src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js">
</script>

</body>

</html>
"""


def render_page(
    content,
    title="KOJA AFRICA"
):
    return render_template_string(
        PAGE,
        content=content,
        title=title,
        is_admin_user=is_admin()
    )


# ============================================================
# HOME
# ============================================================

@app.route("/")
def home():

    content = """
<div class="hero">

<div class="hero-content">

<h1>KOJA AFRICA</h1>

<p>
A focused platform providing three essential
services: academic assignments, driver and
delivery services, and professional CV
generation.
</p>

<a class="btn"
   href="/register">
Create Account
</a>

<a class="btn btn-dark"
   href="/login">
Login
</a>

</div>

</div>


<div class="grid">

<div class="card service-card">

<div>

<span class="service-number">
01
</span>

<h2>Assignments</h2>

<p>
Submit assignment questions, upload supporting
files, monitor progress and receive completed
answers from the administrator.
</p>

</div>

<a class="btn"
   href="/assignments">
Open Assignments
</a>

</div>


<div class="card service-card">

<div>

<span class="service-number">
02
</span>

<h2>Driver & Delivery</h2>

<p>
Find approved online drivers, request a delivery,
and follow the driver's location on a live map
while the delivery is in progress.
</p>

</div>

<a class="btn btn-green"
   href="/drivers">
Find Drivers
</a>

</div>


<div class="card service-card">

<div>

<span class="service-number">
03
</span>

<h2>CV Generation</h2>

<p>
Create a professional CV yourself or allow an
administrator to prepare one for you and generate
it as a PDF document.
</p>

</div>

<a class="btn btn-orange"
   href="/cv">
Create CV
</a>

</div>

</div>
"""

    return render_page(
        content,
        "Home"
    )


# ============================================================
# REGISTER
# ============================================================

@app.route(
    "/register",
    methods=["GET", "POST"]
)
def register():

    if request.method == "POST":

        email = (
            request.form.get(
                "email",
                ""
            )
            .strip()
            .lower()
        )

        password = request.form.get(
            "password",
            ""
        )

        if not email or not password:
            flash(
                "Email and password are required."
            )
            return redirect(
                url_for("register")
            )

        if len(password) < 6:
            flash(
                "Password must contain at least 6 characters."
            )
            return redirect(
                url_for("register")
            )

        result, error = auth_signup(
            email,
            password
        )

        if error:
            flash(
                "Registration failed. "
                + str(error)
            )
            return redirect(
                url_for("register")
            )

        flash(
            "Account created successfully. "
            "You can now login."
        )

        return redirect(
            url_for("login")
        )

    content = """

<div class="card">

<h2>Create Account</h2>

<p class="small">
Use your email and password.
</p>

<form method="POST">

<label>Email</label>

<input type="email"
       name="email"
       autocomplete="email"
       required>

<label>Password</label>

<input type="password"
       name="password"
       minlength="6"
       autocomplete="new-password"
       required>

<button>
Create Account
</button>

</form>

</div>

"""

    return render_page(
        content,
        "Create Account"
    )


# ============================================================
# LOGIN
# ============================================================

@app.route(
    "/login",
    methods=["GET", "POST"]
)
def login():

    if request.method == "POST":

        email = (
            request.form.get(
                "email",
                ""
            )
            .strip()
            .lower()
        )

        password = request.form.get(
            "password",
            ""
        )

        result, error = auth_login(
            email,
            password
        )

        if error:
            flash(
                "Login failed. Check your email "
                "and password."
            )
            return redirect(
                url_for("login")
            )

        auth_user = (
            result.get("user")
            or {}
        )

        session["user"] = {
            "id":
                auth_user.get("id"),
            "email":
                (
                    auth_user.get("email")
                    or email
                )
        }

        session.permanent = True

        return redirect(
            url_for("dashboard")
        )

    content = """

<div class="card">

<h2>Login</h2>

<form method="POST">

<label>Email</label>

<input type="email"
       name="email"
       autocomplete="email"
       required>

<label>Password</label>

<input type="password"
       name="password"
       autocomplete="current-password"
       required>

<button>
Login
</button>

</form>

</div>

"""

    return render_page(
        content,
        "Login"
    )


# ============================================================
# LOGOUT
# ============================================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect(
        url_for("home")
    )


# ============================================================
# DASHBOARD
# ============================================================

@app.route("/dashboard")
@login_required
def dashboard():

    u = current_user()

    content = f"""

<div class="hero">

<div class="hero-content">

<h1>Dashboard</h1>

<p>
{safe(u.get("email"))}
</p>

</div>

</div>


<div class="grid">

<div class="card service-card">

<div>

<span class="service-number">
01
</span>

<h2>Assignments</h2>

<p>
Submit and track your academic assignments.
</p>

</div>

<a class="btn"
   href="/assignments">
Assignments
</a>

</div>


<div class="card service-card">

<div>

<span class="service-number">
02
</span>

<h2>Driver & Delivery</h2>

<p>
Request a driver and track active deliveries.
</p>

</div>

<a class="btn btn-green"
   href="/drivers">
Drivers
</a>

</div>


<div class="card service-card">

<div>

<span class="service-number">
03
</span>

<h2>CV</h2>

<p>
Build and generate a professional CV.
</p>

</div>

<a class="btn btn-orange"
   href="/cv">
Create CV
</a>

</div>

</div>


<div class="card">

<h2>Driver Registration</h2>

<p>
If you want to provide driver and delivery
services, submit your driver information for
administrator approval.
</p>

<a class="btn btn-green"
   href="/drivers/register">
Register as Driver
</a>

</div>

"""

    return render_page(
        content,
        "Dashboard"
    )


# ============================================================
# ASSIGNMENTS
# ============================================================

@app.route("/assignments")
@login_required
def assignments():

    uid = current_user()["id"]

    rows, error = db_get(
        "assignments",
        {
            "student_id":
                f"eq.{uid}",
            "select":
                "*",
            "order":
                "created_at.desc"
        }
    )

    if error:
        flash(
            "Unable to load assignments."
        )
        rows = []

    cards = ""

    for assignment in rows or []:

        assignment_id = safe(
            assignment.get("id")
        )

        cards += f"""

<div class="card">

<h3>
{safe(assignment.get("title")
      or "Assignment")}
</h3>

<p>
<strong>Subject:</strong>
{safe(assignment.get("subject"))}
</p>

<p>
<strong>Status:</strong>

<span class="status">
{safe(
    assignment.get("status")
    or "pending"
)}
</span>

</p>

<a class="btn"
   href="/assignments/{assignment_id}">
View Assignment
</a>

</div>

"""

    content = f"""

<div class="hero">

<div class="hero-content">

<h1>Assignments</h1>

<p>
Submit questions and monitor completed
academic work.
</p>

<a class="btn"
   href="/assignments/new">
New Assignment
</a>

</div>

</div>

{cards or
'<div class="card">No assignments yet.</div>'}

"""

    return render_page(
        content,
        "Assignments"
    )


# ============================================================
# NEW ASSIGNMENT
# ============================================================

@app.route(
    "/assignments/new",
    methods=["GET", "POST"]
)
@login_required
def new_assignment():

    if request.method == "POST":

        uid = current_user()["id"]

        title = (
            request.form.get(
                "title",
                ""
            )
            .strip()
        )

        subject = (
            request.form.get(
                "subject",
                ""
            )
            .strip()
        )

        description = (
            request.form.get(
                "description",
                ""
            )
            .strip()
        )

        question_file = (
            request.files.get(
                "question_file"
            )
        )

        if not title:
            flash(
                "Assignment title is required."
            )
            return redirect(
                request.url
            )

        if not subject:
            flash(
                "Subject is required."
            )
            return redirect(
                request.url
            )

        if not description:
            flash(
                "Question is required."
            )
            return redirect(
                request.url
            )

        admin_note = ""

        if (
            question_file
            and
            question_file.filename
        ):

            info, upload_error = (
                storage_upload(
                    question_file,
                    "assignment-questions"
                )
            )

            if upload_error:
                flash(
                    "Question file upload failed: "
                    + str(upload_error)
                )
                return redirect(
                    request.url
                )

            admin_note = (
                "QUESTION_FILE|"
                + info["path"]
                + "|"
                + info["filename"]
                + "|"
                + info["content_type"]
            )

        data = {
            "id":
                str(uuid.uuid4()),
            "student_id":
                uid,
            "title":
                title,
            "subject":
                subject,
            "description":
                description,
            "status":
                "pending",
            "admin_note":
                admin_note,
            "answer_text":
                None
        }

        result, error = db_insert(
            "assignments",
            data
        )

        if error:
            flash(
                "Assignment could not be saved: "
                + str(error)
            )
            return redirect(
                request.url
            )

        flash(
            "Assignment submitted successfully."
        )

        return redirect(
            url_for("assignments")
        )

    content = """

<div class="card">

<h2>New Assignment</h2>

<form method="POST"
      enctype="multipart/form-data">

<label>Assignment Title</label>

<input name="title"
       required>

<label>Subject</label>

<input name="subject"
       required>

<label>Question</label>

<textarea name="description"
          required></textarea>

<label>
Supporting File
</label>

<input type="file"
       name="question_file"
       accept=".pdf,.doc,.docx,.jpg,.jpeg,.png,.webp">

<button>
Submit Assignment
</button>

</form>

<p class="small">
Maximum upload size: 15 MB.
</p>

</div>

"""

    return render_page(
        content,
        "New Assignment"
    )


# ============================================================
# ASSIGNMENT DETAIL
# ============================================================

@app.route(
    "/assignments/<assignment_id>"
)
@login_required
def assignment_detail(
    assignment_id
):

    uid = current_user()["id"]

    rows, error = db_get(
        "assignments",
        {
            "id":
                f"eq.{assignment_id}",
            "student_id":
                f"eq.{uid}",
            "select":
                "*"
        }
    )

    if error or not rows:
        flash(
            "Assignment not found."
        )
        return redirect(
            url_for("assignments")
        )

    assignment = rows[0]

    answer = (
        assignment.get(
            "answer_text"
        )
        or
        "Your answer has not been completed yet."
    )

    content = f"""

<div class="card">

<h2>
{safe(
    assignment.get("title")
    or "Assignment"
)}
</h2>

<p>
<strong>Subject:</strong>
{safe(assignment.get("subject"))}
</p>

<p>
<strong>Status:</strong>

<span class="status">
{safe(
    assignment.get("status")
    or "pending"
)}
</span>

</p>

<hr>

<h3>Question</h3>

<p>
{safe(
    assignment.get("description")
)}
</p>

</div>


<div class="card">

<h2>Answer</h2>

<p>
{safe(answer)}
</p>

<a class="btn"
   href="/assignment-file/{safe(assignment_id)}/answer">
Download Answer File
</a>

</div>


<a class="btn btn-light"
   href="/assignments">
Back
</a>

"""

    return render_page(
        content,
        "Assignment"
    )


# ============================================================
# ADMIN DASHBOARD
# ============================================================

@app.route("/admin")
@admin_required
def admin():

    assignments_rows, _ = db_get(
        "assignments",
        {
            "select":
                "*",
            "order":
                "created_at.desc"
        }
    )

    driver_rows, _ = db_get(
        "driver_profiles",
        {
            "select":
                "*",
            "order":
                "created_at.desc"
        }
    )

    delivery_rows, _ = db_get(
        "delivery_requests",
        {
            "select":
                "*",
            "order":
                "created_at.desc"
        }
    )

    content = f"""

<div class="hero">

<div class="hero-content">

<h1>Administrator</h1>

<p>
Manage the three KOJA AFRICA services.
</p>

</div>

</div>


<div class="grid">

<div class="card">

<h2>Assignments</h2>

<p>
{len(assignments_rows or [])}
assignment records
</p>

<a class="btn"
   href="/admin/assignments">
Manage Assignments
</a>

</div>


<div class="card">

<h2>Drivers</h2>

<p>
{len(driver_rows or [])}
driver records
</p>

<a class="btn btn-green"
   href="/admin/drivers">
Manage Drivers
</a>

</div>


<div class="card">

<h2>Deliveries</h2>

<p>
{len(delivery_rows or [])}
delivery requests
</p>

<a class="btn btn-green"
   href="/admin/deliveries">
Manage Deliveries
</a>

</div>


<div class="card">

<h2>CV Generation</h2>

<p>
Create a CV on behalf of a user.
</p>

<a class="btn btn-orange"
   href="/admin/cv">
Generate CV
</a>

</div>

</div>

"""

    return render_page(
        content,
        "Administrator"
    )


# ============================================================
# ADMIN ASSIGNMENTS
# ============================================================

@app.route("/admin/assignments")
@admin_required
def admin_assignments():

    rows, error = db_get(
        "assignments",
        {
            "select":
                "*",
            "order":
                "created_at.desc"
        }
    )

    if error:
        flash(
            "Unable to load assignments."
        )
        rows = []

    cards = ""

    for assignment in rows or []:

        assignment_id = safe(
            assignment.get("id")
        )

        cards += f"""

<div class="card">

<h3>
{safe(
    assignment.get("title")
    or "Assignment"
)}
</h3>

<p>
<strong>Student:</strong>
{safe(
    assignment.get("student_id")
)}
</p>

<p>
<strong>Subject:</strong>
{safe(
    assignment.get("subject")
)}
</p>

<p>
<strong>Status:</strong>
{safe(
    assignment.get("status")
    or "pending"
)}
</p>

<a class="btn"
   href="/admin/assignments/{assignment_id}">
Process
</a>

</div>

"""

    content = f"""

<div class="hero">

<div class="hero-content">

<h1>Assignment Management</h1>

</div>

</div>

{cards or
'<div class="card">No assignments.</div>'}

"""

    return render_page(
        content,
        "Assignment Management"
    )


# ============================================================
# ADMIN PROCESS ASSIGNMENT
# ============================================================

@app.route(
    "/admin/assignments/<assignment_id>",
    methods=["GET", "POST"]
)
@admin_required
def admin_assignment(
    assignment_id
):

    rows, error = db_get(
        "assignments",
        {
            "id":
                f"eq.{assignment_id}",
            "select":
                "*"
        }
    )

    if error or not rows:
        flash(
            "Assignment not found."
        )
        return redirect(
            url_for("admin_assignments")
        )

    assignment = rows[0]

    if request.method == "POST":

        status = (
            request.form.get(
                "status",
                "in_progress"
            )
        )

        answer_text = (
            request.form.get(
                "answer_text",
                ""
            )
            .strip()
        )

        note = (
            request.form.get(
                "admin_note",
                ""
            )
            .strip()
        )

        answer_file = (
            request.files.get(
                "answer_file"
            )
        )

        if (
            answer_file
            and
            answer_file.filename
        ):

            info, upload_error = (
                storage_upload(
                    answer_file,
                    "assignment-answers"
                )
            )

            if upload_error:
                flash(
                    "Answer upload failed: "
                    + str(upload_error)
                )
                return redirect(
                    request.url
                )

            note += (
                "\nANSWER_FILE|"
                + info["path"]
                + "|"
                + info["filename"]
                + "|"
                + info["content_type"]
            )

        data = {
            "status":
                status,
            "admin_note":
                note,
            "answer_text":
                answer_text,
            "updated_at":
                now_iso()
        }

        if status in (
            "completed",
            "approved"
        ):
            data["completed_at"] = (
                now_iso()
            )

        result, update_error = (
            db_update(
                "assignments",
                {
                    "id":
                        assignment_id
                },
                data
            )
        )

        if update_error:
            flash(
                "Assignment update failed: "
                + str(update_error)
            )
        else:
            flash(
                "Assignment updated successfully."
            )

        return redirect(
            request.url
        )

    content = f"""

<div class="card">

<h2>
{safe(
    assignment.get("title")
)}
</h2>

<p>
<strong>Subject:</strong>
{safe(
    assignment.get("subject")
)}
</p>

<p>
<strong>Student:</strong>
{safe(
    assignment.get("student_id")
)}
</p>

<h3>Question</h3>

<p>
{safe(
    assignment.get("description")
)}
</p>

</div>


<div class="card">

<h2>Process Assignment</h2>

<form method="POST"
      enctype="multipart/form-data">

<label>Status</label>

<select name="status">

<option value="pending">
Pending
</option>

<option value="in_progress">
In Progress
</option>

<option value="completed">
Completed
</option>

<option value="approved">
Approved
</option>

</select>

<label>Administrator Note</label>

<textarea name="admin_note">{safe(
    assignment.get("admin_note")
)}</textarea>

<label>Written Answer</label>

<textarea name="answer_text">{safe(
    assignment.get("answer_text")
)}</textarea>

<label>Answer PDF / Word File</label>

<input type="file"
       name="answer_file"
       accept=".pdf,.doc,.docx">

<button>
Save Answer
</button>

</form>

</div>

"""

    return render_page(
        content,
        "Process Assignment"
    )


# ============================================================
# ASSIGNMENT FILE DOWNLOAD
# ============================================================

@app.route(
    "/assignment-file/<assignment_id>/<file_type>"
)
@login_required
def assignment_file(
    assignment_id,
    file_type
):

    uid = current_user()["id"]

    params = {
        "id":
            f"eq.{assignment_id}",
        "select":
            "*"
    }

    if not is_admin():
        params["student_id"] = (
            f"eq.{uid}"
        )

    rows, error = db_get(
        "assignments",
        params
    )

    if error or not rows:
        return "File not found", 404

    assignment = rows[0]

    note = (
        assignment.get(
            "admin_note"
        )
        or ""
    )

    marker = (
        "ANSWER_FILE|"
        if file_type == "answer"
        else
        "QUESTION_FILE|"
    )

    path = None
    filename = "download"

    for line in note.splitlines():

        if line.startswith(marker):

            parts = line.split("|")

            if len(parts) >= 3:
                path = parts[1]
                filename = parts[2]

            break

    if not path:
        return "File not found", 404

    content, error = (
        storage_download(path)
    )

    if error:
        return (
            "Unable to download file",
            500
        )

    return send_file(
        BytesIO(content),
        download_name=filename,
        as_attachment=True
    )


# ============================================================
# DRIVER REGISTRATION
# ============================================================

@app.route(
    "/drivers/register",
    methods=["GET", "POST"]
)
@login_required
def driver_register():

    uid = current_user()["id"]

    if request.method == "POST":

        vehicle_type = (
            request.form.get(
                "vehicle_type",
                ""
            )
            .strip()
        )

        vehicle_number = (
            request.form.get(
                "vehicle_number",
                ""
            )
            .strip()
        )

        license_number = (
            request.form.get(
                "license_number",
                ""
            )
            .strip()
        )

        location_name = (
            request.form.get(
                "location_name",
                ""
            )
            .strip()
        )

        if not vehicle_type:
            flash(
                "Vehicle type is required."
            )
            return redirect(
                request.url
            )

        if not vehicle_number:
            flash(
                "Vehicle number is required."
            )
            return redirect(
                request.url
            )

        if not license_number:
            flash(
                "License number is required."
            )
            return redirect(
                request.url
            )

        data = {
            "id":
                str(uuid.uuid4()),
            "provider_id":
                uid,
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
            "latitude":
                None,
            "longitude":
                None,
            "location_name":
                location_name
        }

        result, error = (
            db_insert(
                "driver_profiles",
                data
            )
        )

        if error:
            flash(
                "Driver registration failed: "
                + str(error)
            )
            return redirect(
                request.url
            )

        flash(
            "Driver registration submitted "
            "for administrator approval."
        )

        return redirect(
            url_for("driver_dashboard")
        )

    content = """

<div class="card">

<h2>Driver Registration</h2>

<p>
Submit your information. A driver must be
approved by the administrator before appearing
to customers.
</p>

<form method="POST">

<label>Vehicle Type</label>

<input name="vehicle_type"
       placeholder="Car, motorcycle, van"
       required>

<label>Vehicle Number</label>

<input name="vehicle_number"
       required>

<label>License Number</label>

<input name="license_number"
       required>

<label>Current Location</label>

<input name="location_name"
       placeholder="Example: Kitwe City Centre">

<button class="btn-green">
Submit Registration
</button>

</form>

</div>

"""

    return render_page(
        content,
        "Driver Registration"
    )


# ============================================================
# DRIVER DASHBOARD
# ============================================================

@app.route("/driver")
@login_required
def driver_dashboard():

    uid = current_user()["id"]

    rows, error = db_get(
        "driver_profiles",
        {
            "provider_id":
                f"eq.{uid}",
            "select":
                "*"
        }
    )

    if error or not rows:
        content = """

<div class="card">

<h2>Driver Service</h2>

<p>
You are not registered as a driver yet.
</p>

<a class="btn btn-green"
   href="/drivers/register">
Register as Driver
</a>

</div>

"""

        return render_page(
            content,
            "Driver Dashboard"
        )

    driver = rows[0]

    driver_id = safe(
        driver.get("id")
    )

    status = (
        driver.get("status")
        or "pending"
    )

    online = bool(
        driver.get("is_online")
    )

    latitude = (
        driver.get("latitude")
    )

    longitude = (
        driver.get("longitude")
    )

    content = f"""

<div class="hero">

<div class="hero-content">

<h1>Driver Dashboard</h1>

<p>
Status:
{safe(status)}
</p>

</div>

</div>


<div class="card">

<h2>Driver Status</h2>

<p>

<strong>Approval:</strong>

<span class="status">
{safe(status)}
</span>

</p>

<p>

<strong>Online:</strong>

<span class="status
{
'status-online'
if online else ''
}">
{
'ONLINE'
if online
else
'OFFLINE'
}
</span>

</p>

{% if status == "approved" %}

<form method="POST"
      action="/driver/status">

<input type="hidden"
       name="is_online"
       value="{{
           'false'
           if online
           else
           'true'
       }}">

<button class="btn-green">
{{
    "Go Offline"
    if online
    else
    "Go Online"
}}
</button>

</form>

{% endif %}

</div>


<div class="card">

<h2>Live GPS Tracking</h2>

<p>
Keep this page open while you are online.
Your device GPS position will be sent to KOJA
AFRICA and customers can see your current
location while a delivery is active.
</p>

<div class="map-status">

<span class="live-dot"></span>

<span id="gpsStatus">
GPS waiting to start
</span>

</div>

<div id="driverMap"
     class="map">
</div>

</div>


<script>

const DRIVER_ID =
    "{driver_id}";

let driverMap = null;
let driverMarker = null;
let gpsStarted = false;

function startDriverMap(){

    const initialLat =
        {float(latitude) if latitude is not None else -12.9700};

    const initialLng =
        {float(longitude) if longitude is not None else 28.6333};

    driverMap =
        L.map("driverMap")
         .setView(
             [initialLat, initialLng],
             13
         );

    L.tileLayer(
        "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
        {
            maxZoom:19,
            attribution:
                "&copy; OpenStreetMap contributors"
        }
    ).addTo(driverMap);

    {% if latitude is not none and longitude is not none %}

    driverMarker =
        L.marker(
            [
                {float(latitude)},
                {float(longitude)}
            ]
        )
        .addTo(driverMap)
        .bindPopup(
            "Current driver location"
        );

    {% endif %}
}


function updateGPSStatus(message){

    const element =
        document.getElementById(
            "gpsStatus"
        );

    if(element){
        element.textContent =
            message;
    }
}


function sendLocation(position){

    const latitude =
        position.coords.latitude;

    const longitude =
        position.coords.longitude;

    const accuracy =
        position.coords.accuracy;

    updateGPSStatus(
        "GPS active. Accuracy: "
        +
        Math.round(accuracy)
        +
        " metres"
    );

    if(driverMarker){

        driverMarker.setLatLng(
            [
                latitude,
                longitude
            ]
        );

    }else{

        driverMarker =
            L.marker(
                [
                    latitude,
                    longitude
                ]
            )
            .addTo(driverMap)
            .bindPopup(
                "Current driver location"
            );

    }

    driverMap.setView(
        [
            latitude,
            longitude
        ],
        16
    );

    const form =
        new URLSearchParams();

    form.append(
        "latitude",
        latitude
    );

    form.append(
        "longitude",
        longitude
    );

    form.append(
        "location_name",
        "GPS location"
    );

    fetch(
        "/driver/location",
        {
            method:"POST",
            headers:{
                "Content-Type":
                    "application/x-www-form-urlencoded"
            },
            body:form.toString()
        }
    )
    .then(
        response =>
            response.json()
    )
    .then(
        data => {

            if(data.success){

                updateGPSStatus(
                    "Live location updated"
                );

            }else{

                updateGPSStatus(
                    "Unable to update location"
                );

            }

        }
    )
    .catch(
        () => {

            updateGPSStatus(
                "Network error while updating GPS"
            );

        }
    );
}


function gpsError(error){

    if(error.code === 1){

        updateGPSStatus(
            "GPS permission was denied"
        );

    }else if(error.code === 2){

        updateGPSStatus(
            "GPS position unavailable"
        );

    }else{

        updateGPSStatus(
            "GPS timeout"
        );

    }

}


function startGPS(){

    if(!navigator.geolocation){

        updateGPSStatus(
            "This device does not support GPS"
        );

        return;

    }

    gpsStarted = true;

    updateGPSStatus(
        "Requesting GPS permission..."
    );

    navigator.geolocation.watchPosition(
        sendLocation,
        gpsError,
        {
            enableHighAccuracy:true,
            maximumAge:5000,
            timeout:15000
        }
    );

}


startDriverMap();

{% if online and status == "approved" %}

startGPS();

{% else %}

updateGPSStatus(
    "Go online to start live tracking"
);

{% endif %}

</script>

"""

    return render_page(
        content,
        "Driver Dashboard"
    )


# ============================================================
# DRIVER STATUS
# ============================================================

@app.route(
    "/driver/status",
    methods=["POST"]
)
@login_required
def driver_status():

    uid = current_user()["id"]

    rows, error = db_get(
        "driver_profiles",
        {
            "provider_id":
                f"eq.{uid}",
            "select":
                "*"
        }
    )

    if error or not rows:
        flash(
            "Driver profile not found."
        )
        return redirect(
            url_for("drivers")
        )

    driver = rows[0]

    if (
        driver.get("status")
        != "approved"
    ):
        flash(
            "Your driver account must be approved "
            "before you can go online."
        )
        return redirect(
            url_for("driver_dashboard")
        )

    online = (
        request.form.get(
            "is_online",
            "false"
        ).lower()
        == "true"
    )

    result, update_error = (
        db_update(
            "driver_profiles",
            {
                "id":
                    driver.get("id")
            },
            {
                "is_online":
                    online,
                "updated_at":
                    now_iso()
            }
        )
    )

    if update_error:
        flash(
            "Unable to change driver status."
        )
    else:
        flash(
            "Driver is now "
            +
            (
                "ONLINE."
                if online
                else
                "OFFLINE."
            )
        )

    return redirect(
        url_for("driver_dashboard")
    )


# ============================================================
# DRIVER GPS UPDATE
# ============================================================

@app.route(
    "/driver/location",
    methods=["POST"]
)
@login_required
def driver_location():

    uid = current_user()["id"]

    rows, error = db_get(
        "driver_profiles",
        {
            "provider_id":
                f"eq.{uid}",
            "select":
                "*"
        }
    )

    if error or not rows:
        return jsonify({
            "success":
                False,
            "message":
                "Driver profile not found."
        }), 404

    driver = rows[0]

    if (
        driver.get("status")
        != "approved"
    ):
        return jsonify({
            "success":
                False,
            "message":
                "Driver is not approved."
        }), 403

    try:

        latitude = float(
            request.form.get(
                "latitude"
            )
        )

        longitude = float(
            request.form.get(
                "longitude"
            )
        )

    except Exception:

        return jsonify({
            "success":
                False,
            "message":
                "Invalid GPS coordinates."
        }), 400

    if not (
        -90 <= latitude <= 90
        and
        -180 <= longitude <= 180
    ):
        return jsonify({
            "success":
                False,
            "message":
                "GPS coordinates are out of range."
        }), 400

    location_name = (
        request.form.get(
            "location_name",
            ""
        )
        .strip()
    )

    result, update_error = (
        db_update(
            "driver_profiles",
            {
                "id":
                    driver.get("id")
            },
            {
                "latitude":
                    latitude,
                "longitude":
                    longitude,
                "location_name":
                    location_name,
                "is_online":
                    True,
                "last_location_update":
                    now_iso(),
                "updated_at":
                    now_iso()
            }
        )
    )

    if update_error:
        return jsonify({
            "success":
                False,
            "message":
                update_error
        }), 500

    return jsonify({
        "success":
            True,
        "latitude":
            latitude,
        "longitude":
            longitude
    })


# ============================================================
# AVAILABLE DRIVERS
# ============================================================

@app.route("/drivers")
@login_required
def drivers():

    rows, error = db_get(
        "driver_profiles",
        {
            "status":
                "eq.approved",
            "is_online":
                "eq.true",
            "select":
                "*",
            "order":
                "last_location_update.desc"
        }
    )

    if error:
        flash(
            "Could not load available drivers."
        )
        rows = []

    cards = ""

    for driver in rows or []:

        driver_id = safe(
            driver.get("id")
        )

        latitude = (
            driver.get(
                "latitude"
            )
        )

        longitude = (
            driver.get(
                "longitude"
            )
        )

        cards += f"""

<div class="card">

<h3>
{safe(
    driver.get("vehicle_type")
    or "Driver"
)}
</h3>

<p>
<strong>Vehicle:</strong>
{safe(
    driver.get("vehicle_number")
)}
</p>

<p>
<strong>Location:</strong>
{safe(
    driver.get("location_name")
    or
    "Live GPS available"
)}
</p>

<p class="location-live">
Live tracking available
</p>

<form method="POST"
      action="/delivery/request">

<input type="hidden"
       name="driver_id"
       value="{driver_id}">

<label>Pickup Location</label>

<input name="pickup_location"
       placeholder="Exact pickup location"
       required>

<label>Destination</label>

<input name="destination_location"
       placeholder="Exact destination"
       required>

<label>Request Type</label>

<select name="service_type">

<option value="delivery">
Delivery
</option>

<option value="ride">
Ride
</option>

</select>

<label>Notes</label>

<textarea name="notes"
          placeholder="Additional instructions"></textarea>

<button class="btn-green">
Request Driver
</button>

</form>

</div>

"""

    content = f"""

<div class="hero">

<div class="hero-content">

<h1>Driver & Delivery</h1>

<p>
Approved drivers who are currently online
are displayed below.
</p>

<a class="btn"
   href="/driver">
Driver Dashboard
</a>

<a class="btn btn-dark"
   href="/drivers/register">
Register as Driver
</a>

</div>

</div>


<div class="grid">

{cards or
'<div class="card">No online drivers are currently available.</div>'}

</div>

"""

    return render_page(
        content,
        "Drivers"
    )


# ============================================================
# DELIVERY REQUEST
# ============================================================

@app.route(
    "/delivery/request",
    methods=["POST"]
)
@login_required
def delivery_request():

    uid = current_user()["id"]

    driver_id = (
        request.form.get(
            "driver_id"
        )
        or
        None
    )

    pickup = (
        request.form.get(
            "pickup_location",
            ""
        )
        .strip()
    )

    destination = (
        request.form.get(
            "destination_location",
            ""
        )
        .strip()
    )

    notes = (
        request.form.get(
            "notes",
            ""
        )
        .strip()
    )

    service_type = (
        request.form.get(
            "service_type",
            "delivery"
        )
        .strip()
    )

    if not pickup:
        flash(
            "Pickup location is required."
        )
        return redirect(
            url_for("drivers")
        )

    if not destination:
        flash(
            "Destination is required."
        )
        return redirect(
            url_for("drivers")
        )

    data = {
        "id":
            str(uuid.uuid4()),
        "customer_id":
            uid,
        "driver_id":
            driver_id,
        "pickup_location":
            pickup,
        "delivery_location":
            destination,
        "destination_location":
            destination,
        "latitude":
            None,
        "longitude":
            None,
        "pickup_latitude":
            None,
        "pickup_longitude":
            None,
        "destination_latitude":
            None,
        "destination_longitude":
            None,
        "status":
            "pending",
        "notes":
            notes,
        "service_type":
            service_type,
        "requested_at":
            now_iso()
    }

    result, error = (
        db_insert(
            "delivery_requests",
            data
        )
    )

    if error:
        flash(
            "Delivery request failed: "
            + str(error)
        )
        return redirect(
            url_for("drivers")
        )

    flash(
        "Driver request submitted successfully."
    )

    return redirect(
        url_for("my_deliveries")
    )


# ============================================================
# CUSTOMER DELIVERIES
# ============================================================

@app.route("/deliveries")
@login_required
def my_deliveries():

    uid = current_user()["id"]

    rows, error = db_get(
        "delivery_requests",
        {
            "customer_id":
                f"eq.{uid}",
            "select":
                "*",
            "order":
                "created_at.desc"
        }
    )

    if error:
        flash(
            "Unable to load your deliveries."
        )
        rows = []

    cards = ""

    for delivery in rows or []:

        delivery_id = safe(
            delivery.get("id")
        )

        status = (
            delivery.get("status")
            or
            "pending"
        )

        cards += f"""

<div class="card">

<h3>
{safe(
    (
        delivery.get(
            "service_type"
        )
        or
        "delivery"
    ).title()
)}
</h3>

<p>
<strong>Pickup:</strong>
{safe(
    delivery.get(
        "pickup_location"
    )
)}
</p>

<p>
<strong>Destination:</strong>
{safe(
    delivery.get(
        "destination_location"
    )
    or
    delivery.get(
        "delivery_location"
    )
)}
</p>

<p>
<strong>Status:</strong>

<span class="status">
{safe(status)}
</span>

</p>

<a class="btn btn-green"
   href="/delivery/{delivery_id}">
Track Delivery
</a>

</div>

"""

    content = f"""

<div class="hero">

<div class="hero-content">

<h1>My Deliveries</h1>

<p>
Track your active and previous driver requests.
</p>

</div>

</div>

{cards or
'<div class="card">No delivery requests yet.</div>'}

"""

    return render_page(
        content,
        "My Deliveries"
    )


# ============================================================
# LIVE DELIVERY TRACKING
# ============================================================

@app.route(
    "/delivery/<delivery_id>"
)
@login_required
def delivery_tracking(
    delivery_id
):

    uid = current_user()["id"]

    params = {
        "id":
            f"eq.{delivery_id}",
        "select":
            "*"
    }

    if not is_admin():
        params["customer_id"] = (
            f"eq.{uid}"
        )

    rows, error = db_get(
        "delivery_requests",
        params
    )

    if error or not rows:
        flash(
            "Delivery not found."
        )
        return redirect(
            url_for("my_deliveries")
        )

    delivery = rows[0]

    driver_id = (
        delivery.get(
            "driver_id"
        )
        or
        ""
    )

    content = f"""

<div class="hero">

<div class="hero-content">

<h1>Live Delivery Tracking</h1>

<p>
Follow the driver's latest GPS position
while the delivery is active.
</p>

</div>

</div>


<div class="card">

<h2>
Delivery Details
</h2>

<p>
<strong>Pickup:</strong>
{safe(
    delivery.get(
        "pickup_location"
    )
)}
</p>

<p>
<strong>Destination:</strong>
{safe(
    delivery.get(
        "destination_location"
    )
    or
    delivery.get(
        "delivery_location"
    )
)}
</p>

<p>
<strong>Status:</strong>

<span id="deliveryStatus"
      class="status">

{safe(
    delivery.get(
        "status"
    )
    or
    "pending"
)}

</span>

</p>

<div class="map-status">

<span class="live-dot"></span>

<span id="trackingStatus">
Connecting to live tracking...
</span>

</div>

<div id="deliveryMap"
     class="map">
</div>

</div>


<script>

const DELIVERY_ID =
    "{safe(delivery_id)}";

const DRIVER_ID =
    "{safe(driver_id)}";

let map = null;
let driverMarker = null;


function initMap(){

    map =
        L.map("deliveryMap")
         .setView(
             [-12.9700, 28.6333],
             13
         );

    L.tileLayer(
        "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
        {
            maxZoom:19,
            attribution:
                "&copy; OpenStreetMap contributors"
        }
    ).addTo(map);

}


function setTrackingStatus(
    message
){

    const element =
        document.getElementById(
            "trackingStatus"
        );

    if(element){
        element.textContent =
            message;
    }

}


function updateDriver(){

    if(!DRIVER_ID){

        setTrackingStatus(
            "No driver has been assigned yet."
        );

        return;

    }

    fetch(
        "/api/driver-location/"
        +
        encodeURIComponent(
            DRIVER_ID
        )
    )
    .then(
        response =>
            response.json()
    )
    .then(
        data => {

            if(!data.success){

                setTrackingStatus(
                    "Driver location unavailable."
                );

                return;

            }

            if(
                data.latitude === null
                ||
                data.longitude === null
            ){

                setTrackingStatus(
                    "Waiting for driver GPS."
                );

                return;

            }

            const lat =
                Number(
                    data.latitude
                );

            const lng =
                Number(
                    data.longitude
                );

            const position =
                [lat, lng];

            if(!driverMarker){

                driverMarker =
                    L.marker(
                        position
                    )
                    .addTo(map)
                    .bindPopup(
                        "Driver current location"
                    );

            }else{

                driverMarker.setLatLng(
                    position
                );

            }

            map.setView(
                position,
                16
            );

            setTrackingStatus(
                "Driver location is live."
            );

            if(
                data.status
            ){

                const status =
                    document.getElementById(
                        "deliveryStatus"
                    );

                if(status){
                    status.textContent =
                        data.delivery_status
                        ||
                        status.textContent;
                }

            }

        }
    )
    .catch(
        () => {

            setTrackingStatus(
                "Unable to connect to live tracking."
            );

        }
    );

}


initMap();

updateDriver();

setInterval(
    updateDriver,
    5000
);

</script>

"""

    return render_page(
        content,
        "Live Delivery Tracking"
    )


# ============================================================
# DRIVER LOCATION API FOR CUSTOMERS
# ============================================================

@app.route(
    "/api/driver-location/<driver_id>"
)
@login_required
def api_driver_location(
    driver_id
):

    rows, error = db_get(
        "driver_profiles",
        {
            "id":
                f"eq.{driver_id}",
            "status":
                "eq.approved",
            "select":
                "id,latitude,longitude,"
                "location_name,is_online,"
                "last_location_update"
        }
    )

    if error or not rows:

        return jsonify({
            "success":
                False,
            "message":
                "Driver not found."
        }), 404

    driver = rows[0]

    return jsonify({
        "success":
            True,
        "latitude":
            driver.get(
                "latitude"
            ),
        "longitude":
            driver.get(
                "longitude"
            ),
        "location_name":
            driver.get(
                "location_name"
            ),
        "is_online":
            driver.get(
                "is_online"
            ),
        "last_location_update":
            driver.get(
                "last_location_update"
            )
    })


# ============================================================
# ADMIN DRIVER MANAGEMENT
# ============================================================

@app.route("/admin/drivers")
@admin_required
def admin_drivers():

    rows, error = db_get(
        "driver_profiles",
        {
            "select":
                "*",
            "order":
                "created_at.desc"
        }
    )

    if error:
        flash(
            "Unable to load drivers."
        )
        rows = []

    cards = ""

    for driver in rows or []:

        driver_id = safe(
            driver.get("id")
        )

        cards += f"""

<div class="card">

<h3>
{safe(
    driver.get(
        "vehicle_type"
    )
)}
</h3>

<p>
<strong>Provider:</strong>
{safe(
    driver.get(
        "provider_id"
    )
)}
</p>

<p>
<strong>Vehicle:</strong>
{safe(
    driver.get(
        "vehicle_number"
    )
)}
</p>

<p>
<strong>License:</strong>
{safe(
    driver.get(
        "license_number"
    )
)}
</p>

<p>
<strong>Location:</strong>
{safe(
    driver.get(
        "location_name"
    )
)}
</p>

<p>
<strong>Approval:</strong>
{safe(
    driver.get(
        "status"
    )
)}
</p>

<p>
<strong>Online:</strong>
{{
    "Yes"
    if driver.get("is_online")
    else
    "No"
}}
</p>

<form method="POST"
      action="/admin/drivers/{driver_id}">

<label>Approval Status</label>

<select name="status">

<option value="pending">
Pending
</option>

<option value="approved">
Approved
</option>

<option value="rejected">
Rejected
</option>

</select>

<button class="btn-green">
Save
</button>

</form>

</div>

"""

    content = f"""

<div class="hero">

<div class="hero-content">

<h1>Driver Management</h1>

<p>
Approve drivers and monitor their live status.
</p>

</div>

</div>


<div class="grid">

{cards or
'<div class="card">No driver registrations.</div>'}

</div>

"""

    return render_page(
        content,
        "Driver Management"
    )


# ============================================================
# ADMIN DRIVER UPDATE
# ============================================================

@app.route(
    "/admin/drivers/<driver_id>",
    methods=["POST"]
)
@admin_required
def admin_driver_update(
    driver_id
):

    status = (
        request.form.get(
            "status",
            "pending"
        )
    )

    result, error = (
        db_update(
            "driver_profiles",
            {
                "id":
                    driver_id
            },
            {
                "status":
                    status,
                "updated_at":
                    now_iso()
            }
        )
    )

    flash(
        "Driver updated successfully."
        if not error
        else
        "Driver update failed."
    )

    return redirect(
        url_for("admin_drivers")
    )


# ============================================================
# ADMIN DELIVERY MANAGEMENT
# ============================================================

@app.route("/admin/deliveries")
@admin_required
def admin_deliveries():

    rows, error = db_get(
        "delivery_requests",
        {
            "select":
                "*",
            "order":
                "created_at.desc"
        }
    )

    if error:
        flash(
            "Unable to load deliveries."
        )
        rows = []

    cards = ""

    for delivery in rows or []:

        delivery_id = safe(
            delivery.get("id")
        )

        cards += f"""

<div class="card">

<h3>
{safe(
    (
        delivery.get(
            "service_type"
        )
        or
        "delivery"
    ).title()
)}
</h3>

<p>
<strong>Customer:</strong>
{safe(
    delivery.get(
        "customer_id"
    )
)}
</p>

<p>
<strong>Pickup:</strong>
{safe(
    delivery.get(
        "pickup_location"
    )
)}
</p>

<p>
<strong>Destination:</strong>
{safe(
    delivery.get(
        "destination_location"
    )
    or
    delivery.get(
        "delivery_location"
    )
)}
</p>

<p>
<strong>Driver:</strong>
{safe(
    delivery.get(
        "driver_id"
    )
    or
    "Not assigned"
)}
</p>

<p>
<strong>Status:</strong>
{safe(
    delivery.get(
        "status"
    )
)}
</p>

<form method="POST"
      action="/admin/deliveries/{delivery_id}">

<label>Driver ID</label>

<input name="driver_id"
       value="{safe(
           delivery.get(
               "driver_id"
           )
           or
           ""
       )}"
       placeholder="Driver profile ID">

<label>Status</label>

<select name="status">

<option value="pending">
Pending
</option>

<option value="accepted">
Accepted
</option>

<option value="started">
Started
</option>

<option value="completed">
Completed
</option>

<option value="cancelled">
Cancelled
</option>

</select>

<button class="btn-green">
Update Delivery
</button>

</form>

<a class="btn"
   href="/delivery/{delivery_id}">
Open Live Map
</a>

</div>

"""

    content = f"""

<div class="hero">

<div class="hero-content">

<h1>Delivery Management</h1>

<p>
Assign drivers and update delivery progress.
</p>

</div>

</div>


<div class="grid">

{cards or
'<div class="card">No delivery requests.</div>'}

</div>

"""

    return render_page(
        content,
        "Delivery Management"
    )


# ============================================================
# ADMIN DELIVERY UPDATE
# ============================================================

@app.route(
    "/admin/deliveries/<delivery_id>",
    methods=["POST"]
)
@admin_required
def admin_delivery_update(
    delivery_id
):

    driver_id = (
        request.form.get(
            "driver_id",
            ""
        )
        .strip()
    )

    status = (
        request.form.get(
            "status",
            "pending"
        )
    )

    data = {
        "status":
            status,
        "updated_at":
            now_iso()
    }

    if driver_id:
        data["driver_id"] = (
            driver_id
        )
    else:
        data["driver_id"] = None

    if status == "accepted":
        data["accepted_at"] = (
            now_iso()
        )

    elif status == "started":
        data["started_at"] = (
            now_iso()
        )

    elif status == "completed":
        data["completed_at"] = (
            now_iso()
        )

    result, error = (
        db_update(
            "delivery_requests",
            {
                "id":
                    delivery_id
            },
            data
        )
    )

    flash(
        "Delivery updated successfully."
        if not error
        else
        "Delivery update failed."
    )

    return redirect(
        url_for("admin_deliveries")
    )


# ============================================================
# CV GENERATOR
# ============================================================

CV_TEMPLATE = """

<div class="hero">

<div class="hero-content">

<h1>CV Generator</h1>

<p>
Create a professional CV and generate it as a
PDF document. You can prepare it yourself or
an administrator can prepare it for you.
</p>

</div>

</div>


<div class="card">

<form method="POST"
      action="/cv/generate">

<div class="section-title">
Personal Information
</div>

<label>Full Name</label>

<input name="full_name"
       required>

<label>Phone</label>

<input name="phone"
       required>

<label>Email</label>

<input type="email"
       name="email"
       value="{{ user_email }}"
       required>

<label>Location</label>

<input name="location"
       placeholder="City, Country">


<div class="cv-section">

<div class="section-title">
Professional Profile
</div>

<label>Professional Title</label>

<input name="professional_title"
       placeholder="Teacher, Accountant, Driver, etc.">

<label>Professional Summary</label>

<textarea name="summary"
          placeholder="Write a short professional summary"></textarea>

</div>


<div class="cv-section">

<div class="section-title">
Education
</div>

<label>Education History</label>

<textarea name="education"
          placeholder="Qualification, institution and year"></textarea>

</div>


<div class="cv-section">

<div class="section-title">
Work Experience
</div>

<label>Work Experience</label>

<textarea name="experience"
          placeholder="Position, company, responsibilities and dates"></textarea>

</div>


<div class="cv-section">

<div class="section-title">
Skills
</div>

<label>Skills</label>

<textarea name="skills"
          placeholder="List your main skills"></textarea>

</div>


<div class="cv-section">

<div class="section-title">
Certifications
</div>

<label>Certifications</label>

<textarea name="certifications"></textarea>

</div>


<div class="cv-section">

<div class="section-title">
References
</div>

<label>References</label>

<textarea name="references"></textarea>

</div>


<button class="btn-orange">
Generate CV PDF
</button>

</form>

</div>

"""


@app.route("/cv")
@login_required
def cv():

    content = render_template_string(
        CV_TEMPLATE,
        user_email=safe(
            current_user().get(
                "email"
            )
        )
    )

    return render_page(
        content,
        "CV Generator"
    )


# ============================================================
# CV PDF GENERATION
# ============================================================

def generate_cv_pdf(data):

    if not REPORTLAB_AVAILABLE:
        return None, (
            "ReportLab is not installed."
        )

    buffer = BytesIO()

    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=45,
        leftMargin=45,
        topMargin=40,
        bottomMargin=40
    )

    styles = (
        getSampleStyleSheet()
    )

    name_style = ParagraphStyle(
        "CVName",
        parent=styles["Title"],
        fontSize=24,
        leading=28,
        alignment=TA_LEFT,
        spaceAfter=8
    )

    title_style = ParagraphStyle(
        "CVTitle",
        parent=styles["Normal"],
        fontSize=12,
        leading=16,
        textColor=colors.HexColor(
            "#475569"
        ),
        spaceAfter=14
    )

    heading_style = ParagraphStyle(
        "CVHeading",
        parent=styles["Heading2"],
        fontSize=13,
        leading=16,
        textColor=colors.HexColor(
            "#1d4ed8"
        ),
        spaceBefore=12,
        spaceAfter=6
    )

    body_style = ParagraphStyle(
        "CVBody",
        parent=styles["BodyText"],
        fontSize=10,
        leading=15,
        spaceAfter=5
    )

    story = []

    full_name = (
        data.get(
            "full_name"
        )
        or
        "Curriculum Vitae"
    )

    professional_title = (
        data.get(
            "professional_title"
        )
        or
        ""
    )

    contact = " | ".join(
        value
        for value in [
            data.get("phone"),
            data.get("email"),
            data.get("location")
        ]
        if value
    )

    story.append(
        Paragraph(
            safe(full_name),
            name_style
        )
    )

    if professional_title:
        story.append(
            Paragraph(
                safe(
                    professional_title
                ),
                title_style
            )
        )

    if contact:
        story.append(
            Paragraph(
                safe(contact),
                body_style
            )
        )

    story.append(
        HRFlowable(
            width="100%",
            thickness=1,
            color=colors.HexColor(
                "#cbd5e1"
            ),
            spaceBefore=6,
            spaceAfter=10
        )
    )

    sections = [
        (
            "PROFESSIONAL PROFILE",
            data.get("summary")
        ),
        (
            "EDUCATION",
            data.get("education")
        ),
        (
            "WORK EXPERIENCE",
            data.get("experience")
        ),
        (
            "SKILLS",
            data.get("skills")
        ),
        (
            "CERTIFICATIONS",
            data.get("certifications")
        ),
        (
            "REFERENCES",
            data.get("references")
        )
    ]

    for heading, value in sections:

        if not value:
            continue

        story.append(
            Paragraph(
                heading,
                heading_style
            )
        )

        paragraphs = str(
            value
        ).splitlines()

        for paragraph in paragraphs:

            paragraph = (
                paragraph.strip()
            )

            if paragraph:

                story.append(
                    Paragraph(
                        safe(
                            paragraph
                        ),
                        body_style
                    )
                )

    story.append(
        Spacer(
            1,
            20
        )
    )

    story.append(
        Paragraph(
            "Generated by KOJA AFRICA",
            ParagraphStyle(
                "Footer",
                parent=styles["Normal"],
                fontSize=8,
                textColor=colors.HexColor(
                    "#64748b"
                )
            )
        )
    )

    document.build(story)

    buffer.seek(0)

    return buffer, None


# ============================================================
# SELF CV GENERATION
# ============================================================

@app.route(
    "/cv/generate",
    methods=["POST"]
)
@login_required
def cv_generate():

    user_email = (
        current_user().get(
            "email"
        )
    )

    data = {
        "full_name":
            request.form.get(
                "full_name",
                ""
            ).strip(),

        "phone":
            request.form.get(
                "phone",
                ""
            ).strip(),

        "email":
            request.form.get(
                "email",
                ""
            ).strip()
            or
            user_email,

        "location":
            request.form.get(
                "location",
                ""
            ).strip(),

        "professional_title":
            request.form.get(
                "professional_title",
                ""
            ).strip(),

        "summary":
            request.form.get(
                "summary",
                ""
            ).strip(),

        "education":
            request.form.get(
                "education",
                ""
            ).strip(),

        "experience":
            request.form.get(
                "experience",
                ""
            ).strip(),

        "skills":
            request.form.get(
                "skills",
                ""
            ).strip(),

        "certifications":
            request.form.get(
                "certifications",
                ""
            ).strip(),

        "references":
            request.form.get(
                "references",
                ""
            ).strip()
    }

    if not data["full_name"]:
        flash(
            "Full name is required."
        )
        return redirect(
            url_for("cv")
        )

    if not data["phone"]:
        flash(
            "Phone number is required."
        )
        return redirect(
            url_for("cv")
        )

    if not data["email"]:
        flash(
            "Email is required."
        )
        return redirect(
            url_for("cv")
        )

    pdf, error = (
        generate_cv_pdf(
            data
        )
    )

    if error:
        flash(error)
        return redirect(
            url_for("cv")
        )

    filename = (
        secure_filename(
            data["full_name"]
        )
        or
        "KOJA_CV"
    )

    filename += ".pdf"

    return send_file(
        pdf,
        mimetype="application/pdf",
        download_name=filename,
        as_attachment=True
    )


# ============================================================
# ADMIN CV GENERATION
# ============================================================

@app.route(
    "/admin/cv",
    methods=["GET", "POST"]
)
@admin_required
def admin_cv():

    if request.method == "POST":

        data = {
            "full_name":
                request.form.get(
                    "full_name",
                    ""
                ).strip(),

            "phone":
                request.form.get(
                    "phone",
                    ""
                ).strip(),

            "email":
                request.form.get(
                    "email",
                    ""
                ).strip(),

            "location":
                request.form.get(
                    "location",
                    ""
                ).strip(),

            "professional_title":
                request.form.get(
                    "professional_title",
                    ""
                ).strip(),

            "summary":
                request.form.get(
                    "summary",
                    ""
                ).strip(),

            "education":
                request.form.get(
                    "education",
                    ""
                ).strip(),

            "experience":
                request.form.get(
                    "experience",
                    ""
                ).strip(),

            "skills":
                request.form.get(
                    "skills",
                    ""
                ).strip(),

            "certifications":
                request.form.get(
                    "certifications",
                    ""
                ).strip(),

            "references":
                request.form.get(
                    "references",
                    ""
                ).strip()
        }

        if not data["full_name"]:
            flash(
                "Full name is required."
            )
            return redirect(
                request.url
            )

        pdf, error = (
            generate_cv_pdf(
                data
            )
        )

        if error:
            flash(error)
            return redirect(
                request.url
            )

        filename = (
            secure_filename(
                data["full_name"]
            )
            or
            "KOJA_CV"
        )

        filename += ".pdf"

        return send_file(
            pdf,
            mimetype="application/pdf",
            download_name=filename,
            as_attachment=True
        )

    content = """

<div class="hero">

<div class="hero-content">

<h1>Administrator CV Generator</h1>

<p>
Create a professional CV on behalf of a
customer or applicant.
</p>

</div>

</div>


<div class="card">

<form method="POST">

<div class="section-title">
Personal Information
</div>

<label>Full Name</label>

<input name="full_name"
       required>

<label>Phone</label>

<input name="phone"
       required>

<label>Email</label>

<input type="email"
       name="email"
       required>

<label>Location</label>

<input name="location">


<div class="cv-section">

<div class="section-title">
Professional Profile
</div>

<label>Professional Title</label>

<input name="professional_title">

<label>Professional Summary</label>

<textarea name="summary"></textarea>

</div>


<div class="cv-section">

<div class="section-title">
Education
</div>

<textarea name="education"></textarea>

</div>


<div class="cv-section">

<div class="section-title">
Work Experience
</div>

<textarea name="experience"></textarea>

</div>


<div class="cv-section">

<div class="section-title">
Skills
</div>

<textarea name="skills"></textarea>

</div>


<div class="cv-section">

<div class="section-title">
Certifications
</div>

<textarea name="certifications"></textarea>

</div>


<div class="cv-section">

<div class="section-title">
References
</div>

<textarea name="references"></textarea>

</div>


<button class="btn-orange">
Generate Customer CV
</button>

</form>

</div>

"""

    return render_page(
        content,
        "Admin CV Generator"
    )


# ============================================================
# HEALTH CHECK
# ============================================================

@app.route("/health")
def health():

    return jsonify({
        "status":
            "ok",

        "application":
            "KOJA AFRICA",

        "services": [
            "assignments",
            "driver_delivery",
            "cv_generation"
        ],

        "features": {
            "live_driver_tracking":
                True,

            "live_delivery_map":
                True,

            "self_cv_generation":
                True,

            "admin_cv_generation":
                True
        },

        "database_configured":
            configuration_ok()
    })


# ============================================================
# ERROR HANDLERS
# ============================================================

@app.errorhandler(404)
def error_404(error):

    return render_page(
        """

<div class="card">

<h2>Page not found</h2>

<p>
The requested page does not exist.
</p>

<a class="btn"
   href="/">
Return Home
</a>

</div>

""",
        "Not Found"
    ), 404


@app.errorhandler(500)
def error_500(error):

    logger.exception(
        "Internal server error"
    )

    return render_page(
        """

<div class="card">

<h2>Server Error</h2>

<p>
The server encountered an unexpected error.
Check the Render logs for the exact error.
</p>

<a class="btn"
   href="/">
Return Home
</a>

</div>

""",
        "Server Error"
    ), 500


# ============================================================
# START APPLICATION
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

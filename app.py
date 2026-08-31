import os
import uuid
import logging
from io import BytesIO
from datetime import datetime, timezone
from functools import wraps

import requests
from dotenv import load_dotenv
from flask import (
    Flask, request, redirect, url_for, session,
    render_template_string, flash, jsonify, send_file
)
from werkzeug.utils import secure_filename

load_dotenv()

# ============================================================
# KOJA AFRICA
# THREE SERVICES ONLY
#
# 1. ASSIGNMENTS
# 2. DRIVER + DELIVERY + LIVE GPS MAP
# 3. CV BUILDER
# ============================================================

app = Flask(__name__)
app.secret_key = os.getenv(
    "FLASK_SECRET_KEY",
    "CHANGE_THIS_SECRET"
)

app.config["PERMANENT_SESSION_LIFETIME"] = 86400 * 30

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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("koja-africa")


# ============================================================
# HELPERS
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


def api_headers(prefer=None):
    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization":
            f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json"
    }

    if prefer:
        headers["Prefer"] = prefer

    return headers


def allowed_file(filename):
    if not filename or "." not in filename:
        return False

    extension = filename.rsplit(
        ".",
        1
    )[1].lower()

    return extension in ALLOWED_EXTENSIONS


def esc(value):
    """
    Basic HTML escaping for values inserted into templates.
    """
    if value is None:
        return ""

    text = str(value)

    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#039;")
    )


# ============================================================
# SUPABASE DATABASE
# ============================================================

def db_get(table, params=None):
    try:
        response = requests.get(
            f"{SUPABASE_URL}/rest/v1/{table}",
            headers=api_headers(),
            params=params or {},
            timeout=30
        )

        if not response.ok:
            logger.error(
                "GET %s: %s",
                table,
                response.text
            )
            return None, response.text

        return response.json(), None

    except Exception as error:
        logger.exception(
            "Supabase GET error"
        )
        return None, str(error)


def db_insert(table, data):
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
                "INSERT %s: %s",
                table,
                response.text
            )
            return None, response.text

        try:
            return response.json(), None
        except Exception:
            return [], None

    except Exception as error:
        logger.exception(
            "Supabase INSERT error"
        )
        return None, str(error)


def db_update(table, filters, data):
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
                "UPDATE %s: %s",
                table,
                response.text
            )
            return None, response.text

        try:
            return response.json(), None
        except Exception:
            return [], None

    except Exception as error:
        logger.exception(
            "Supabase UPDATE error"
        )
        return None, str(error)


# ============================================================
# AUTHENTICATION
# EMAIL + PASSWORD ONLY
# ============================================================

def auth_signup(email, password):
    try:
        response = requests.post(
            f"{SUPABASE_URL}/auth/v1/signup",
            headers={
                "apikey": SUPABASE_SERVICE_KEY,
                "Content-Type": "application/json"
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

    except Exception as error:
        return None, str(error)


def auth_login(email, password):
    try:
        response = requests.post(
            f"{SUPABASE_URL}/auth/v1/token?grant_type=password",
            headers={
                "apikey": SUPABASE_SERVICE_KEY,
                "Content-Type": "application/json"
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

    except Exception as error:
        return None, str(error)


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
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization":
            f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": content_type,
        "x-upsert": "false"
    }

    try:
        response = requests.post(
            f"{SUPABASE_URL}/storage/v1/object/"
            f"{SUPABASE_BUCKET}/{object_name}",
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

    except Exception as error:
        logger.exception(
            "Storage error"
        )
        return None, str(error)


def storage_download(path):
    try:
        response = requests.get(
            f"{SUPABASE_URL}/storage/v1/object/"
            f"{SUPABASE_BUCKET}/{path}",
            headers={
                "apikey": SUPABASE_SERVICE_KEY,
                "Authorization":
                    f"Bearer {SUPABASE_SERVICE_KEY}"
            },
            timeout=60
        )

        if not response.ok:
            return None, response.text

        return response.content, None

    except Exception as error:
        return None, str(error)


# ============================================================
# SESSION
# ============================================================

def current_user():
    return session.get("user")


def logged_in():
    return bool(current_user())


def is_admin():
    user_data = current_user()

    if not user_data:
        return False

    email = (
        user_data.get("email", "")
        .strip()
        .lower()
    )

    return bool(
        ADMIN_EMAIL
        and
        email == ADMIN_EMAIL
    )


def login_required(function):
    @wraps(function)
    def wrapper(*args, **kwargs):

        if not logged_in():
            flash(
                "Please login to continue."
            )
            return redirect(
                url_for("login")
            )

        return function(
            *args,
            **kwargs
        )

    return wrapper


def admin_required(function):
    @wraps(function)
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

        return function(
            *args,
            **kwargs
        )

    return wrapper


# ============================================================
# PROFESSIONAL UI
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
      content="#07111f">

<title>
{{ title }} | KOJA AFRICA
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
    background:#f4f7fb;
    color:#172033;
    font-family:
        Inter,
        Arial,
        Helvetica,
        sans-serif;
    overflow-x:hidden;
}

/* =========================
   ANIMATION
========================= */

@keyframes fadeUp{
    from{
        opacity:0;
        transform:translateY(22px);
    }
    to{
        opacity:1;
        transform:translateY(0);
    }
}

@keyframes fadeIn{
    from{
        opacity:0;
    }
    to{
        opacity:1;
    }
}

@keyframes pulse{
    0%{
        box-shadow:
            0 0 0 0
            rgba(37,99,235,.35);
    }

    70%{
        box-shadow:
            0 0 0 15px
            rgba(37,99,235,0);
    }

    100%{
        box-shadow:
            0 0 0 0
            rgba(37,99,235,0);
    }
}

@keyframes float{
    0%,100%{
        transform:translateY(0);
    }

    50%{
        transform:translateY(-7px);
    }
}

.animate{
    animation:
        fadeUp .65s ease both;
}

.delay1{
    animation-delay:.08s;
}

.delay2{
    animation-delay:.16s;
}

.delay3{
    animation-delay:.24s;
}

.delay4{
    animation-delay:.32s;
}

/* =========================
   NAVIGATION
========================= */

.navbar{
    position:sticky;
    top:0;
    z-index:1000;

    background:
        rgba(7,17,31,.94);

    backdrop-filter:
        blur(16px);

    border-bottom:
        1px solid
        rgba(255,255,255,.08);

    color:white;
}

.nav-inner{
    max-width:1180px;
    margin:auto;
    padding:15px 20px;

    display:flex;
    align-items:center;
    justify-content:space-between;
    gap:20px;
}

.brand{
    color:white;
    text-decoration:none;
    font-size:22px;
    font-weight:800;
    letter-spacing:.4px;
}

.brand span{
    color:#4f9cff;
}

.nav-links{
    display:flex;
    gap:6px;
    flex-wrap:wrap;
    justify-content:flex-end;
}

.nav-links a{
    color:#dce7f5;
    text-decoration:none;
    padding:9px 11px;
    border-radius:8px;
    font-size:14px;
    transition:.25s;
}

.nav-links a:hover{
    background:
        rgba(255,255,255,.09);
    color:white;
}

/* =========================
   CONTAINER
========================= */

.container{
    width:min(1180px,94%);
    margin:auto;
    padding:28px 0 50px;
}

/* =========================
   HERO
========================= */

.hero{
    position:relative;
    overflow:hidden;

    background:
        linear-gradient(
            135deg,
            #07111f,
            #123b68 55%,
            #2563eb
        );

    color:white;

    border-radius:24px;

    padding:46px 34px;

    margin-bottom:24px;

    box-shadow:
        0 20px 50px
        rgba(10,40,80,.16);

    animation:
        fadeUp .7s ease both;
}

.hero:before{
    content:"";
    position:absolute;

    width:260px;
    height:260px;

    border-radius:50%;

    background:
        rgba(255,255,255,.07);

    right:-90px;
    top:-100px;

    animation:
        float 5s ease-in-out infinite;
}

.hero:after{
    content:"";
    position:absolute;

    width:140px;
    height:140px;

    border-radius:50%;

    background:
        rgba(255,255,255,.05);

    left:-50px;
    bottom:-70px;
}

.hero-content{
    position:relative;
    z-index:2;
}

.hero h1{
    margin:0 0 12px;
    font-size:
        clamp(30px,6vw,56px);
    line-height:1.05;
}

.hero p{
    max-width:700px;
    color:#dbeafe;
    line-height:1.7;
    font-size:16px;
}

/* =========================
   GRID
========================= */

.grid{
    display:grid;

    grid-template-columns:
        repeat(
            auto-fit,
            minmax(270px,1fr)
        );

    gap:20px;
}

/* =========================
   CARDS
========================= */

.card{
    background:white;

    border:
        1px solid
        #e6ebf2;

    border-radius:18px;

    padding:23px;

    margin-bottom:18px;

    box-shadow:
        0 7px 25px
        rgba(17,24,39,.055);

    animation:
        fadeUp .6s ease both;

    transition:
        transform .25s,
        box-shadow .25s,
        border-color .25s;
}

.card:hover{
    transform:
        translateY(-3px);

    box-shadow:
        0 15px 35px
        rgba(17,24,39,.09);

    border-color:
        #d7e2f1;
}

.card h2{
    margin-top:0;
}

.card h3{
    margin-top:0;
}

.muted{
    color:#697586;
}

.small{
    font-size:13px;
    color:#718096;
}

.divider{
    height:1px;
    background:#e8edf3;
    margin:20px 0;
}

/* =========================
   BUTTONS
========================= */

.btn,
button{
    border:0;

    border-radius:10px;

    padding:12px 18px;

    background:#2563eb;

    color:white;

    text-decoration:none;

    cursor:pointer;

    display:inline-block;

    font-size:14px;

    font-weight:600;

    transition:
        transform .2s,
        box-shadow .2s,
        background .2s;
}

.btn:hover,
button:hover{
    transform:
        translateY(-2px);

    box-shadow:
        0 8px 20px
        rgba(37,99,235,.20);
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
    background:#edf3fa;
    color:#17324d;
}

.btn-full{
    width:100%;
    text-align:center;
}

/* =========================
   FORMS
========================= */

label{
    display:block;

    font-size:13px;

    font-weight:700;

    margin:
        12px 0 6px;

    color:#344054;
}

input,
textarea,
select{
    width:100%;

    padding:13px 14px;

    border:
        1px solid
        #d8e0ea;

    border-radius:10px;

    background:#fff;

    color:#172033;

    font-size:15px;

    outline:none;

    transition:
        border .2s,
        box-shadow .2s;
}

input:focus,
textarea:focus,
select:focus{
    border-color:#2563eb;

    box-shadow:
        0 0 0 3px
        rgba(37,99,235,.10);
}

textarea{
    min-height:140px;
    resize:vertical;
}

/* =========================
   SERVICE CARDS
========================= */

.service-card{
    position:relative;
    overflow:hidden;
}

.service-number{
    font-size:12px;
    font-weight:800;
    color:#2563eb;
    letter-spacing:1px;
    margin-bottom:12px;
}

.service-card h2{
    font-size:22px;
}

.service-card p{
    color:#697586;
    line-height:1.65;
}

/* =========================
   STATUS
========================= */

.status{
    display:inline-block;

    padding:
        6px 11px;

    border-radius:999px;

    font-size:12px;

    font-weight:700;

    background:#edf1f5;
}

.status-pending{
    background:#fff7ed;
    color:#c2410c;
}

.status-approved,
.status-accepted,
.status-completed{
    background:#ecfdf5;
    color:#047857;
}

.status-rejected,
.status-cancelled{
    background:#fef2f2;
    color:#b91c1c;
}

.status-started,
.status-in_progress{
    background:#eff6ff;
    color:#1d4ed8;
}

.live{
    display:inline-flex;
    align-items:center;
    gap:8px;
    color:#047857;
    font-weight:700;
}

.live-dot{
    width:9px;
    height:9px;
    border-radius:50%;
    background:#10b981;
    animation:
        pulse 1.7s infinite;
}

/* =========================
   MAP
========================= */

#map{
    width:100%;
    height:430px;

    border-radius:16px;

    overflow:hidden;

    border:
        1px solid
        #dce4ee;

    animation:
        fadeIn .8s ease both;
}

.map-card{
    padding:0;
    overflow:hidden;
}

.map-header{
    padding:18px 20px;
    background:#fff;
}

/* =========================
   STATS
========================= */

.stat-grid{
    display:grid;

    grid-template-columns:
        repeat(
            auto-fit,
            minmax(150px,1fr)
        );

    gap:14px;
}

.stat{
    background:white;
    border:1px solid #e5eaf0;
    border-radius:14px;
    padding:18px;
}

.stat strong{
    display:block;
    font-size:26px;
    margin-bottom:5px;
}

/* =========================
   FLASH
========================= */

.flash{
    background:#fff8eb;
    border:1px solid #fed7aa;
    color:#92400e;

    padding:13px 15px;

    border-radius:11px;

    margin-bottom:12px;

    animation:
        fadeUp .45s ease both;
}

/* =========================
   TABLE
========================= */

.table-wrap{
    overflow-x:auto;
}

table{
    width:100%;
    border-collapse:collapse;
}

th,
td{
    padding:12px;
    text-align:left;
    border-bottom:
        1px solid #edf0f4;
    font-size:14px;
}

th{
    color:#475467;
}

/* =========================
   CV PREVIEW
========================= */

.cv-preview{
    background:#fff;
    border:1px solid #dce3ec;
    padding:35px;
    border-radius:4px;
    box-shadow:
        0 12px 35px
        rgba(0,0,0,.07);
}

.cv-name{
    font-size:34px;
    font-weight:800;
    color:#111827;
}

.cv-title{
    color:#2563eb;
    font-weight:700;
    margin-top:5px;
}

.cv-section{
    margin-top:25px;
}

.cv-section h3{
    border-bottom:
        2px solid #111827;
    padding-bottom:7px;
    font-size:15px;
    text-transform:uppercase;
    letter-spacing:.7px;
}

/* =========================
   FOOTER
========================= */

footer{
    background:#07111f;
    color:#9fb0c3;
    text-align:center;
    padding:30px 20px;
    line-height:1.7;
}

footer strong{
    color:white;
}

/* =========================
   MOBILE
========================= */

@media(max-width:700px){

    .nav-inner{
        align-items:flex-start;
        flex-direction:column;
    }

    .nav-links{
        justify-content:flex-start;
    }

    .hero{
        padding:34px 23px;
        border-radius:18px;
    }

    .card{
        padding:19px;
    }

    #map{
        height:350px;
    }

    .cv-preview{
        padding:22px;
    }

}

</style>

</head>

<body>

<nav class="navbar">

<div class="nav-inner">

<a class="brand"
   href="/">
   KOJA <span>AFRICA</span>
</a>

<div class="nav-links">

<a href="/">Home</a>

{% if session.get("user") %}

<a href="/dashboard">
Dashboard
</a>

<a href="/assignments">
Assignments
</a>

<a href="/drivers">
Drivers
</a>

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

<strong>KOJA AFRICA</strong><br>

Assignments |
Driver & Delivery |
CV Services

</footer>

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

<div class="service-number">
KOJA AFRICA
</div>

<h1>
Practical services for everyday needs.
</h1>

<p>
KOJA AFRICA brings assignments,
driver and delivery services,
and professional CV creation
together in one simple platform.
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

<div class="card service-card delay1">

<div class="service-number">
SERVICE 01
</div>

<h2>
Assignments
</h2>

<p>
Submit assignments and academic
questions, upload supporting files,
and receive completed answers
through your account.
</p>

<a class="btn"
   href="/assignments">
Open Assignments
</a>

</div>

<div class="card service-card delay2">

<div class="service-number">
SERVICE 02
</div>

<h2>
Driver & Delivery
</h2>

<p>
Request a driver or delivery and
track an active driver using
live GPS location on the map.
</p>

<a class="btn btn-green"
   href="/drivers">
Find a Driver
</a>

</div>

<div class="card service-card delay3">

<div class="service-number">
SERVICE 03
</div>

<h2>
CV Services
</h2>

<p>
Create a professional CV yourself
or submit your information for
administrator-assisted CV creation.
</p>

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

        email = request.form.get(
            "email",
            ""
        ).strip().lower()

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

<h2>
Create Account
</h2>

<p class="muted">
Use only your email address and password.
</p>

<form method="POST">

<label>
Email
</label>

<input
    type="email"
    name="email"
    autocomplete="email"
    required
>

<label>
Password
</label>

<input
    type="password"
    name="password"
    minlength="6"
    autocomplete="new-password"
    required
>

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

        email = request.form.get(
            "email",
            ""
        ).strip().lower()

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
                "Login failed. Check your email and password."
            )

            return redirect(
                url_for("login")
            )

        auth_user = (
            result.get("user")
            or {}
        )

        session["user"] = {
            "id": auth_user.get("id"),
            "email":
                auth_user.get("email")
                or
                email
        }

        session.permanent = True

        return redirect(
            url_for("dashboard")
        )

    content = """
<div class="card">

<h2>
Login
</h2>

<form method="POST">

<label>
Email
</label>

<input
    type="email"
    name="email"
    autocomplete="email"
    required
>

<label>
Password
</label>

<input
    type="password"
    name="password"
    autocomplete="current-password"
    required
>

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

    email = esc(
        current_user().get("email")
    )

    content = f"""
<div class="hero">

<div class="hero-content">

<div class="service-number">
MY ACCOUNT
</div>

<h1>
Welcome back.
</h1>

<p>
{email}
</p>

</div>

</div>

<div class="grid">

<div class="card delay1">

<h2>
Assignments
</h2>

<p class="muted">
Submit and manage your academic work.
</p>

<a class="btn"
   href="/assignments">
Open
</a>

</div>

<div class="card delay2">

<h2>
Driver & Delivery
</h2>

<p class="muted">
Request a driver and follow active
delivery tracking.
</p>

<a class="btn btn-green"
   href="/drivers">
Open
</a>

</div>

<div class="card delay3">

<h2>
CV Services
</h2>

<p class="muted">
Create your own professional CV
or request administrator assistance.
</p>

<a class="btn btn-orange"
   href="/cv">
Open
</a>

</div>

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
            "select": "*",
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

        status = (
            assignment.get("status")
            or
            "pending"
        )

        status_class = (
            "status-" +
            str(status).lower()
            .replace(" ", "_")
        )

        cards += f"""

<div class="card">

<h3>
{esc(
    assignment.get("title")
    or
    "Assignment"
)}
</h3>

<p class="muted">
Subject:
{esc(
    assignment.get("subject")
    or
    ""
)}
</p>

<span class="status {status_class}">
{esc(status)}
</span>

<br><br>

<a class="btn"
   href="/assignments/{assignment.get("id")}">
View
</a>

</div>

"""

    content = f"""

<div class="hero">

<div class="hero-content">

<div class="service-number">
SERVICE 01
</div>

<h1>
Assignments
</h1>

<p>
Submit academic questions and track
the progress of your work.
</p>

<a class="btn"
   href="/assignments/new">
New Assignment
</a>

</div>

</div>

<div class="grid">

{cards or
'''
<div class="card">
<h3>No assignments yet.</h3>
<p class="muted">
Create your first assignment.
</p>
</div>
'''}

</div>
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

        title = request.form.get(
            "title",
            ""
        ).strip()

        subject = request.form.get(
            "subject",
            ""
        ).strip()

        description = request.form.get(
            "description",
            ""
        ).strip()

        question_file = request.files.get(
            "question_file"
        )

        if not title or not subject or not description:

            flash(
                "Title, subject and question are required."
            )

            return redirect(
                url_for("new_assignment")
            )

        admin_note = ""

        if (
            question_file
            and
            question_file.filename
        ):

            info, upload_error = storage_upload(
                question_file,
                "assignment-questions"
            )

            if upload_error:

                flash(
                    "Question file upload failed: "
                    + str(upload_error)
                )

                return redirect(
                    url_for("new_assignment")
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
            "id": str(uuid.uuid4()),
            "student_id": uid,
            "title": title,
            "subject": subject,
            "description": description,
            "status": "pending",
            "admin_note": admin_note,
            "answer_text": None
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
                url_for("new_assignment")
            )

        flash(
            "Assignment submitted successfully."
        )

        return redirect(
            url_for("assignments")
        )

    content = """

<div class="card">

<h2>
New Assignment
</h2>

<form method="POST"
      enctype="multipart/form-data">

<label>
Assignment Title
</label>

<input
    name="title"
    required
>

<label>
Subject
</label>

<input
    name="subject"
    required
>

<label>
Question
</label>

<textarea
    name="description"
    required
></textarea>

<label>
Supporting File
</label>

<input
    type="file"
    name="question_file"
    accept=".pdf,.doc,.docx,.jpg,.jpeg,.png,.webp"
>

<button>
Submit Assignment
</button>

</form>

<p class="small">
Maximum file size: 15 MB.
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
            "select": "*"
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
{esc(
    assignment.get("title")
)}
</h2>

<p>
<strong>Subject:</strong>
{esc(
    assignment.get("subject")
)}
</p>

<p>
<strong>Status:</strong>
<span class="status">
{esc(
    assignment.get("status")
    or
    "pending"
)}
</span>
</p>

<div class="divider"></div>

<h3>
Question
</h3>

<p>
{esc(
    assignment.get("description")
)}
</p>

</div>

<div class="card">

<h2>
Answer
</h2>

<p>
{esc(answer)}
</p>

</div>

"""

    return render_page(
        content,
        "Assignment"
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

        vehicle_type = request.form.get(
            "vehicle_type",
            ""
        ).strip()

        vehicle_number = request.form.get(
            "vehicle_number",
            ""
        ).strip()

        license_number = request.form.get(
            "license_number",
            ""
        ).strip()

        location_name = request.form.get(
            "location_name",
            ""
        ).strip()

        if not vehicle_type:

            flash(
                "Vehicle type is required."
            )

            return redirect(
                request.url
            )

        data = {
            "id": str(uuid.uuid4()),
            "provider_id": uid,
            "vehicle_type": vehicle_type,
            "vehicle_number": vehicle_number,
            "license_number": license_number,
            "status": "pending",
            "is_online": False,
            "latitude": None,
            "longitude": None,
            "location_name": location_name
        }

        result, error = db_insert(
            "driver_profiles",
            data
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
            "Driver registration submitted for approval."
        )

        return redirect(
            url_for("driver_dashboard")
        )

    content = """

<div class="hero">

<div class="hero-content">

<div class="service-number">
DRIVER SERVICE
</div>

<h1>
Register as a Driver
</h1>

<p>
After approval, you can go online,
share your GPS location and receive
delivery requests.
</p>

</div>

</div>

<div class="card">

<form method="POST">

<label>
Vehicle Type
</label>

<input
    name="vehicle_type"
    placeholder="Car, motorcycle, van"
    required
>

<label>
Vehicle Number
</label>

<input
    name="vehicle_number"
    required
>

<label>
License Number
</label>

<input
    name="license_number"
    required
>

<label>
Current Location
</label>

<input
    name="location_name"
    placeholder="Example: Kitwe City Centre"
    required
>

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
            "select": "*",
            "order":
                "created_at.desc"
        }
    )

    if error or not rows:

        content = """

<div class="card">

<h2>
Driver Registration
</h2>

<p class="muted">
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
            "Driver"
        )

    driver = rows[0]

    approved = (
        str(
            driver.get("status")
        ).lower()
        ==
        "approved"
    )

    online = bool(
        driver.get("is_online")
    )

    if not approved:

        content = f"""

<div class="card">

<h2>
Driver Application
</h2>

<p>
Status:
<span class="status">
{esc(
    driver.get("status")
    or
    "pending"
)}
</span>
</p>

<p class="muted">
Your driver account must be approved
before you can receive delivery requests.
</p>

</div>

"""

        return render_page(
            content,
            "Driver"
        )

    online_text = (
        "ONLINE"
        if online
        else
        "OFFLINE"
    )

    content = f"""

<div class="hero">

<div class="hero-content">

<div class="service-number">
DRIVER CONTROL
</div>

<h1>
Driver Dashboard
</h1>

<p>
{esc(
    driver.get("vehicle_type")
)}
&nbsp;
{esc(
    driver.get("vehicle_number")
)}
</p>

<div class="live">

<span class="live-dot"></span>

<span id="driverState">
{online_text}
</span>

</div>

</div>

</div>

<div class="grid">

<div class="card">

<h2>
Availability
</h2>

<p class="muted">
Go online to allow customers to
see your current location.
</p>

<form method="POST"
      action="/driver/status">

<input type="hidden"
       name="is_online"
       value="true">

<button class="btn-green">
Go Online
</button>

</form>

<br>

<form method="POST"
      action="/driver/status">

<input type="hidden"
       name="is_online"
       value="false">

<button class="btn-dark">
Go Offline
</button>

</form>

</div>

<div class="card">

<h2>
GPS Location
</h2>

<p id="gpsStatus"
   class="muted">
Waiting for GPS permission...
</p>

<p>
Location:
<strong id="driverLocation">
{esc(
    driver.get("location_name")
    or
    "Not available"
)}
</strong>
</p>

</div>

</div>

<div class="card map-card">

<div class="map-header">

<h2>
Live Driver Map
</h2>

<p class="small">
Your GPS location is updated while
you are online.
</p>

</div>

<div id="map"></div>

</div>

<script>

let map = L.map("map")
    .setView(
        [-13.9626, 28.0646],
        6
    );

L.tileLayer(
    "https://{{"{"}}s{{"}"}}.tile.openstreetmap.org/{{"{"}}z{{"}"}}/{{"{"}}x{{"}"}}/{{"{"}}y{{"}"}}.png",
    {{
        maxZoom: 19,
        attribution:
            "&copy; OpenStreetMap contributors"
    }}
).addTo(map);

let marker = null;

function sendLocation(
    position
){{
    const latitude =
        position.coords.latitude;

    const longitude =
        position.coords.longitude;

    const status =
        document.getElementById(
            "gpsStatus"
        );

    status.textContent =
        "GPS location is active.";

    if(!marker){{
        marker =
            L.marker(
                [latitude,longitude]
            ).addTo(map);

        map.setView(
            [latitude,longitude],
            16
        );
    }}else{{
        marker.setLatLng(
            [latitude,longitude]
        );
    }}

    const formData =
        new FormData();

    formData.append(
        "latitude",
        latitude
    );

    formData.append(
        "longitude",
        longitude
    );

    formData.append(
        "location_name",
        document.getElementById(
            "driverLocation"
        ).textContent
    );

    fetch(
        "/driver/location",
        {{
            method:"POST",
            body:formData
        }}
    )
    .then(
        response => response.json()
    )
    .then(
        data => {{
            if(data.success){{
                document.getElementById(
                    "gpsStatus"
                ).textContent =
                    "Location updated.";
            }}
        }}
    )
    .catch(
        () => {{
            document.getElementById(
                "gpsStatus"
            ).textContent =
                "GPS update failed.";
        }}
    );
}}

function gpsError(error){{
    document.getElementById(
        "gpsStatus"
    ).textContent =
        "GPS permission or location unavailable.";
}}

if(
    navigator.geolocation
){{
    navigator.geolocation.watchPosition(
        sendLocation,
        gpsError,
        {{
            enableHighAccuracy:true,
            maximumAge:5000,
            timeout:15000
        }}
    );
}}else{{
    document.getElementById(
        "gpsStatus"
    ).textContent =
        "This device does not support GPS.";
}}

</script>

<script src=
"https://unpkg.com/leaflet@1.9.4/dist/leaflet.js">
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

    online = (
        request.form.get(
            "is_online",
            "false"
        ).lower()
        ==
        "true"
    )

    rows, error = db_get(
        "driver_profiles",
        {
            "provider_id":
                f"eq.{uid}",
            "status":
                "eq.approved",
            "select":
                "id"
        }
    )

    if error or not rows:

        flash(
            "Approved driver profile not found."
        )

        return redirect(
            url_for("driver_dashboard")
        )

    db_update(
        "driver_profiles",
        {
            "id":
                rows[0]["id"]
        },
        {
            "is_online":
                online,
            "updated_at":
                now_iso()
        }
    )

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
            "status":
                "eq.approved",
            "select":
                "id"
        }
    )

    if error or not rows:

        return jsonify({
            "success": False,
            "message":
                "Driver profile not found."
        }), 404

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
            "success": False,
            "message":
                "Invalid coordinates."
        }), 400

    location_name = request.form.get(
        "location_name",
        ""
    ).strip()

    result, error = db_update(
        "driver_profiles",
        {
            "id":
                rows[0]["id"]
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

    if error:

        return jsonify({
            "success": False,
            "message": error
        }), 500

    return jsonify({
        "success": True,
        "latitude": latitude,
        "longitude": longitude
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
        rows = []

    cards = ""

    for driver in rows or []:

        cards += f"""

<div class="card">

<h3>
{esc(
    driver.get("vehicle_type")
    or
    "Driver"
)}
</h3>

<p>
Vehicle:
{esc(
    driver.get("vehicle_number")
)}
</p>

<p class="live">
<span class="live-dot"></span>
Online
</p>

<p class="muted">
{esc(
    driver.get("location_name")
    or
    "Current location available on map"
)}
</p>

<form method="POST"
      action="/delivery/request">

<input type="hidden"
       name="driver_id"
       value="{esc(driver.get("id"))}">

<label>
Pickup Location
</label>

<input
    name="pickup_location"
    required
>

<label>
Destination
</label>

<input
    name="destination_location"
    required
>

<label>
Instructions
</label>

<textarea
    name="notes"
></textarea>

<button class="btn-green">
Request Driver
</button>

</form>

</div>

"""

    content = f"""

<div class="hero">

<div class="hero-content">

<div class="service-number">
SERVICE 02
</div>

<h1>
Driver & Delivery
</h1>

<p>
Approved drivers who are currently
online can receive delivery requests.
Active deliveries can be followed
using live GPS tracking.
</p>

<a class="btn btn-green"
   href="/driver">
Driver Dashboard
</a>

<a class="btn btn-dark"
   href="/drivers/register">
Register as Driver
</a>

</div>

</div>

<div class="card">

<h2>
Available Drivers
</h2>

<p class="muted">
Only approved and online drivers are shown.
</p>

</div>

<div class="grid">

{cards or
'''
<div class="card">
<h3>
No online drivers available.
</h3>
<p class="muted">
Please check again later.
</p>
</div>
'''}

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

    driver_id = request.form.get(
        "driver_id"
    ) or None

    pickup = request.form.get(
        "pickup_location",
        ""
    ).strip()

    destination = request.form.get(
        "destination_location",
        ""
    ).strip()

    notes = request.form.get(
        "notes",
        ""
    ).strip()

    if not pickup or not destination:

        flash(
            "Pickup and destination are required."
        )

        return redirect(
            url_for("drivers")
        )

    data = {
        "id": str(uuid.uuid4()),
        "customer_id": uid,
        "driver_id": driver_id,
        "pickup_location": pickup,
        "delivery_location": destination,
        "destination_location":
            destination,
        "latitude": None,
        "longitude": None,
        "pickup_latitude": None,
        "pickup_longitude": None,
        "destination_latitude": None,
        "destination_longitude": None,
        "status": "pending",
        "notes": notes,
        "service_type": "delivery",
        "requested_at": now_iso()
    }

    result, error = db_insert(
        "delivery_requests",
        data
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
        "Driver request submitted."
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
        rows = []

    cards = ""

    for delivery in rows or []:

        delivery_id = delivery.get(
            "id"
        )

        status = (
            delivery.get("status")
            or
            "pending"
        )

        active = status in {
            "accepted",
            "started"
        }

        cards += f"""

<div class="card">

<h3>
Delivery Request
</h3>

<p>
<strong>Pickup:</strong>
{esc(
    delivery.get(
        "pickup_location"
    )
)}
</p>

<p>
<strong>Destination:</strong>
{esc(
    delivery.get(
        "destination_location"
    )
)}
</p>

<p>
<strong>Status:</strong>

<span class="status">
{esc(status)}
</span>

</p>

"""

        if active:

            cards += f"""

<a class="btn btn-green"
   href="/delivery/{delivery_id}/track">
Track Live Driver
</a>

"""

        cards += """

</div>

"""

    content = f"""

<div class="hero">

<div class="hero-content">

<div class="service-number">
MY DELIVERIES
</div>

<h1>
Delivery Tracking
</h1>

<p>
View your requests and open live
tracking when a driver has accepted
or started your delivery.
</p>

</div>

</div>

<div class="grid">

{cards or
'''
<div class="card">
<h3>
No delivery requests yet.
</h3>
</div>
'''}

</div>

"""

    return render_page(
        content,
        "My Deliveries"
    )


# ============================================================
# LIVE DELIVERY TRACKING
# ============================================================

@app.route(
    "/delivery/<delivery_id>/track"
)
@login_required
def delivery_track(delivery_id):

    uid = current_user()["id"]

    rows, error = db_get(
        "delivery_requests",
        {
            "id":
                f"eq.{delivery_id}",
            "customer_id":
                f"eq.{uid}",
            "select":
                "*"
        }
    )

    if error or not rows:

        flash(
            "Delivery not found."
        )

        return redirect(
            url_for("my_deliveries")
        )

    delivery = rows[0]

    content = f"""

<div class="hero">

<div class="hero-content">

<div class="service-number">
LIVE DELIVERY
</div>

<h1>
Driver Tracking
</h1>

<p>
Pickup:
{esc(
    delivery.get("pickup_location")
)}
</p>

<p>
Destination:
{esc(
    delivery.get("destination_location")
)}
</p>

<div class="live">
<span class="live-dot"></span>
Live GPS Tracking
</div>

</div>

</div>

<div class="card map-card">

<div class="map-header">

<h2>
Live Driver Location
</h2>

<p id="trackingStatus"
   class="muted">
Connecting to live GPS...
</p>

</div>

<div id="map"></div>

</div>

<div class="card">

<h3>
Delivery Status
</h3>

<p>
Current status:
<strong id="deliveryStatus">
{esc(
    delivery.get("status")
    or
    "pending"
)}
</strong>
</p>

<p class="muted">
The map automatically refreshes while
the delivery is active.
</p>

</div>

<script src=
"https://unpkg.com/leaflet@1.9.4/dist/leaflet.js">
</script>

<script>

const deliveryId =
"{esc(delivery_id)}";

let map =
L.map("map")
.setView(
    [-13.9626,28.0646],
    6
);

L.tileLayer(
    "https://{{"{"}}s{{"}"}}.tile.openstreetmap.org/{{"{"}}z{{"}"}}/{{"{"}}x{{"}"}}/{{"{"}}y{{"}}"}}.png",
    {{
        maxZoom:19,
        attribution:
        "&copy; OpenStreetMap contributors"
    }}
).addTo(map);

let driverMarker = null;

function loadTracking(){{

    fetch(
        "/api/delivery/"
        +
        deliveryId
    )
    .then(
        response =>
            response.json()
    )
    .then(
        data => {{

            if(!data.success){{
                document.getElementById(
                    "trackingStatus"
                ).textContent =
                    "Tracking unavailable.";
                return;
            }}

            document.getElementById(
                "deliveryStatus"
            ).textContent =
                data.status || "pending";

            if(
                data.latitude !== null
                &&
                data.longitude !== null
            ){{

                const position = [
                    data.latitude,
                    data.longitude
                ];

                if(!driverMarker){{

                    driverMarker =
                        L.marker(
                            position
                        )
                        .addTo(map);

                    driverMarker.bindPopup(
                        "Driver location"
                    );

                    map.setView(
                        position,
                        16
                    );

                }}else{{

                    driverMarker.setLatLng(
                        position
                    );

                }}

                document.getElementById(
                    "trackingStatus"
                ).textContent =
                    "Driver location updated.";

            }}else{{

                document.getElementById(
                    "trackingStatus"
                ).textContent =
                    "Waiting for driver GPS location.";

            }}

        }}
    )
    .catch(
        () => {{
            document.getElementById(
                "trackingStatus"
            ).textContent =
                "Connection temporarily unavailable.";
        }}
    );

}}

loadTracking();

setInterval(
    loadTracking,
    5000
);

</script>

"""

    return render_page(
        content,
        "Live Delivery Tracking"
    )


# ============================================================
# DELIVERY API
# ============================================================

@app.route(
    "/api/delivery/<delivery_id>"
)
@login_required
def delivery_api(delivery_id):

    uid = current_user()["id"]

    rows, error = db_get(
        "delivery_requests",
        {
            "id":
                f"eq.{delivery_id}",
            "customer_id":
                f"eq.{uid}",
            "select":
                "*"
        }
    )

    if error or not rows:

        return jsonify({
            "success": False
        }), 404

    delivery = rows[0]

    latitude = delivery.get(
        "latitude"
    )

    longitude = delivery.get(
        "longitude"
    )

    driver_id = delivery.get(
        "driver_id"
    )

    if driver_id:

        driver_rows, driver_error = db_get(
            "driver_profiles",
            {
                "id":
                    f"eq.{driver_id}",
                "select":
                    "latitude,longitude,location_name,is_online,last_location_update"
            }
        )

        if (
            not driver_error
            and
            driver_rows
        ):

            driver = driver_rows[0]

            latitude = driver.get(
                "latitude"
            )

            longitude = driver.get(
                "longitude"
            )

            return jsonify({
                "success": True,
                "status":
                    delivery.get(
                        "status"
                    ),
                "latitude":
                    latitude,
                "longitude":
                    longitude,
                "location_name":
                    driver.get(
                        "location_name"
                    ),
                "is_online":
                    driver.get(
                        "is_online"
                    ),
                "last_update":
                    driver.get(
                        "last_location_update"
                    )
            })

    return jsonify({
        "success": True,
        "status":
            delivery.get(
                "status"
            ),
        "latitude":
            latitude,
        "longitude":
            longitude
    })


# ============================================================
# DRIVER DELIVERY REQUESTS
# ============================================================

@app.route(
    "/driver/deliveries"
)
@login_required
def driver_deliveries():

    uid = current_user()["id"]

    driver_rows, error = db_get(
        "driver_profiles",
        {
            "provider_id":
                f"eq.{uid}",
            "status":
                "eq.approved",
            "select":
                "id"
        }
    )

    if error or not driver_rows:

        flash(
            "Approved driver profile not found."
        )

        return redirect(
            url_for("driver_dashboard")
        )

    driver_id = driver_rows[0]["id"]

    rows, error = db_get(
        "delivery_requests",
        {
            "driver_id":
                f"eq.{driver_id}",
            "select":
                "*",
            "order":
                "created_at.desc"
        }
    )

    if error:
        rows = []

    cards = ""

    for delivery in rows or []:

        cards += f"""

<div class="card">

<h3>
Delivery Request
</h3>

<p>
Pickup:
<strong>
{esc(
    delivery.get(
        "pickup_location"
    )
)}
</strong>
</p>

<p>
Destination:
<strong>
{esc(
    delivery.get(
        "destination_location"
    )
)}
</strong>
</p>

<p>
Status:
<span class="status">
{esc(
    delivery.get(
        "status"
    )
    or
    "pending"
)}
</span>
</p>

<form method="POST"
      action="/driver/delivery/{delivery.get("id")}/status">

<select name="status">

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

</div>

"""

    content = f"""

<div class="hero">

<div class="hero-content">

<h1>
My Delivery Requests
</h1>

<p>
Manage delivery requests assigned to you.
</p>

</div>

</div>

<div class="grid">

{cards or
'''
<div class="card">
<h3>
No delivery requests.
</h3>
</div>
'''}

</div>

"""

    return render_page(
        content,
        "Driver Deliveries"
    )


# ============================================================
# DRIVER DELIVERY STATUS
# ============================================================

@app.route(
    "/driver/delivery/<delivery_id>/status",
    methods=["POST"]
)
@login_required
def driver_delivery_status(
    delivery_id
):

    uid = current_user()["id"]

    driver_rows, error = db_get(
        "driver_profiles",
        {
            "provider_id":
                f"eq.{uid}",
            "status":
                "eq.approved",
            "select":
                "id"
        }
    )

    if error or not driver_rows:

        flash(
            "Driver profile not found."
        )

        return redirect(
            url_for("driver_dashboard")
        )

    driver_id = driver_rows[0]["id"]

    delivery_rows, error = db_get(
        "delivery_requests",
        {
            "id":
                f"eq.{delivery_id}",
            "driver_id":
                f"eq.{driver_id}",
            "select":
                "id"
        }
    )

    if error or not delivery_rows:

        flash(
            "Delivery request not found."
        )

        return redirect(
            url_for("driver_deliveries")
        )

    status = request.form.get(
        "status",
        "accepted"
    )

    data = {
        "status":
            status,
        "updated_at":
            now_iso()
    }

    if status == "accepted":
        data["accepted_at"] = now_iso()

    elif status == "started":
        data["started_at"] = now_iso()

    elif status == "completed":
        data["completed_at"] = now_iso()

    result, update_error = db_update(
        "delivery_requests",
        {
            "id":
                delivery_id
        },
        data
    )

    flash(
        "Delivery status updated."
        if not update_error
        else
        "Delivery update failed."
    )

    return redirect(
        url_for("driver_deliveries")
    )


# ============================================================
# CV SERVICE
#
# User can:
# - create CV themselves
# - generate professional PDF
#
# Admin can:
# - view CV requests
# - generate CV for a user
#
# The PDF is generated directly by the server.
# ============================================================

@app.route(
    "/cv",
    methods=["GET", "POST"]
)
@login_required
def cv_builder():

    if request.method == "POST":

        cv = {
            "name":
                request.form.get(
                    "name",
                    ""
                ).strip(),

            "phone":
                request.form.get(
                    "phone",
                    ""
                ).strip(),

            "email":
                current_user()["email"],

            "address":
                request.form.get(
                    "address",
                    ""
                ).strip(),

            "title":
                request.form.get(
                    "title",
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

            "references":
                request.form.get(
                    "references",
                    ""
                ).strip()
        }

        if not cv["name"]:

            flash(
                "Full name is required."
            )

            return redirect(
                url_for("cv_builder")
            )

        session["cv_data"] = cv

        flash(
            "CV information saved. Review your CV below."
        )

        return redirect(
            url_for("cv_preview")
        )

    content = """

<div class="hero">

<div class="hero-content">

<div class="service-number">
SERVICE 03
</div>

<h1>
Professional CV Builder
</h1>

<p>
Create your CV yourself using the
professional KOJA AFRICA template.
Your email is taken automatically
from your account.
</p>

</div>

</div>

<div class="card">

<form method="POST">

<label>
Full Name
</label>

<input
    name="name"
    required
>

<label>
Phone
</label>

<input
    name="phone"
>

<label>
Address
</label>

<input
    name="address"
>

<label>
Professional Title
</label>

<input
    name="title"
    placeholder="Example: Biology Teacher"
>

<label>
Professional Summary
</label>

<textarea
    name="summary"
    placeholder="Brief professional profile"
></textarea>

<label>
Education
</label>

<textarea
    name="education"
    placeholder="Qualification, institution, year"
></textarea>

<label>
Work Experience
</label>

<textarea
    name="experience"
    placeholder="Position, employer, responsibilities, dates"
></textarea>

<label>
Skills
</label>

<textarea
    name="skills"
    placeholder="Communication, leadership, computer skills..."
></textarea>

<label>
References
</label>

<textarea
    name="references"
    placeholder="Reference name, position, contact"
></textarea>

<button class="btn-orange">
Generate CV
</button>

</form>

</div>

<div class="card">

<h2>
Administrator CV Service
</h2>

<p class="muted">
If you do not want to prepare the CV yourself,
submit your information to KOJA AFRICA and
an administrator can prepare the CV for you.
</p>

<a class="btn btn-dark"
   href="/cv/admin-request">
Request Admin CV
</a>

</div>

"""

    return render_page(
        content,
        "CV Builder"
    )


# ============================================================
# CV PREVIEW
# ============================================================

@app.route("/cv/preview")
@login_required
def cv_preview():

    cv = session.get(
        "cv_data"
    )

    if not cv:

        flash(
            "Create your CV information first."
        )

        return redirect(
            url_for("cv_builder")
        )

    skills = [
        item.strip()
        for item in
        cv.get("skills", "").split(",")
        if item.strip()
    ]

    skills_html = ""

    for skill in skills:
        skills_html += (
            f"<li>{esc(skill)}</li>"
        )

    content = f"""

<div class="card">

<div class="cv-preview">

<div class="cv-name">
{esc(cv.get("name"))}
</div>

<div class="cv-title">
{esc(cv.get("title"))}
</div>

<p>
{esc(cv.get("email"))}
<br>
{esc(cv.get("phone"))}
<br>
{esc(cv.get("address"))}
</p>

<div class="cv-section">

<h3>
Professional Summary
</h3>

<p>
{esc(cv.get("summary"))}
</p>

</div>

<div class="cv-section">

<h3>
Education
</h3>

<p>
{esc(cv.get("education"))}
</p>

</div>

<div class="cv-section">

<h3>
Work Experience
</h3>

<p>
{esc(cv.get("experience"))}
</p>

</div>

<div class="cv-section">

<h3>
Skills
</h3>

<ul>
{skills_html}
</ul>

</div>

<div class="cv-section">

<h3>
References
</h3>

<p>
{esc(cv.get("references"))}
</p>

</div>

</div>

<br>

<a class="btn btn-orange"
   href="/cv/download">
Download Professional CV
</a>

<a class="btn btn-light"
   href="/cv">
Edit CV
</a>

</div>

"""

    return render_page(
        content,
        "CV Preview"
    )


# ============================================================
# CV PDF
# ============================================================

def generate_cv_pdf(cv):

    try:

        from reportlab.lib.pagesizes import A4
        from reportlab.platypus import (
            SimpleDocTemplate,
            Paragraph,
            Spacer,
            Table,
            TableStyle
        )
        from reportlab.lib.styles import (
            getSampleStyleSheet,
            ParagraphStyle
        )
        from reportlab.lib import colors
        from reportlab.lib.enums import (
            TA_LEFT
        )

    except Exception as error:

        logger.exception(
            "ReportLab unavailable"
        )

        raise error

    output = BytesIO()

    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        rightMargin=45,
        leftMargin=45,
        topMargin=45,
        bottomMargin=45
    )

    styles = getSampleStyleSheet()

    name_style = ParagraphStyle(
        "CVName",
        parent=styles["Title"],
        fontSize=25,
        leading=30,
        alignment=TA_LEFT,
        spaceAfter=5
    )

    title_style = ParagraphStyle(
        "CVTitle",
        parent=styles["Normal"],
        fontSize=12,
        leading=16,
        textColor=colors.HexColor(
            "#2563eb"
        ),
        spaceAfter=12
    )

    heading_style = ParagraphStyle(
        "CVHeading",
        parent=styles["Heading3"],
        fontSize=11,
        leading=14,
        spaceBefore=14,
        spaceAfter=7
    )

    body_style = ParagraphStyle(
        "CVBody",
        parent=styles["BodyText"],
        fontSize=9.5,
        leading=14,
        spaceAfter=5
    )

    story = []

    story.append(
        Paragraph(
            esc(cv.get("name")),
            name_style
        )
    )

    story.append(
        Paragraph(
            esc(cv.get("title")),
            title_style
        )
    )

    contact = (
        f"{esc(cv.get('email'))} | "
        f"{esc(cv.get('phone'))} | "
        f"{esc(cv.get('address'))}"
    )

    story.append(
        Paragraph(
            contact,
            body_style
        )
    )

    sections = [
        (
            "PROFESSIONAL SUMMARY",
            cv.get("summary")
        ),
        (
            "EDUCATION",
            cv.get("education")
        ),
        (
            "WORK EXPERIENCE",
            cv.get("experience")
        ),
        (
            "SKILLS",
            cv.get("skills")
        ),
        (
            "REFERENCES",
            cv.get("references")
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

        lines = str(
            value
        ).splitlines()

        for line in lines:

            if line.strip():

                story.append(
                    Paragraph(
                        esc(line),
                        body_style
                    )
                )

    story.append(
        Spacer(1, 20)
    )

    story.append(
        Paragraph(
            "Generated with KOJA AFRICA CV Services",
            ParagraphStyle(
                "Footer",
                parent=body_style,
                fontSize=8,
                textColor=colors.grey
            )
        )
    )

    document.build(story)

    output.seek(0)

    return output


@app.route("/cv/download")
@login_required
def cv_download():

    cv = session.get(
        "cv_data"
    )

    if not cv:

        flash(
            "Create your CV first."
        )

        return redirect(
            url_for("cv_builder")
        )

    try:

        pdf = generate_cv_pdf(
            cv
        )

    except Exception:

        return (
            "CV generation requires ReportLab. "
            "Install reportlab.",
            500
        )

    safe_name = secure_filename(
        cv.get("name")
        or
        "KOJA-CV"
    )

    return send_file(
        pdf,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=(
            safe_name
            +
            "-CV.pdf"
        )
    )


# ============================================================
# ADMIN CV REQUEST
#
# Uses the existing assignments table as the request queue,
# avoiding dependence on an additional CV database table.
# ============================================================

@app.route(
    "/cv/admin-request",
    methods=["GET", "POST"]
)
@login_required
def cv_admin_request():

    if request.method == "POST":

        uid = current_user()["id"]

        name = request.form.get(
            "name",
            ""
        ).strip()

        phone = request.form.get(
            "phone",
            ""
        ).strip()

        title = request.form.get(
            "title",
            ""
        ).strip()

        education = request.form.get(
            "education",
            ""
        ).strip()

        experience = request.form.get(
            "experience",
            ""
        ).strip()

        skills = request.form.get(
            "skills",
            ""
        ).strip()

        summary = request.form.get(
            "summary",
            ""
        ).strip()

        references = request.form.get(
            "references",
            ""
        ).strip()

        description = f"""
CV ADMIN REQUEST

Full Name:
{name}

Phone:
{phone}

Professional Title:
{title}

Professional Summary:
{summary}

Education:
{education}

Work Experience:
{experience}

Skills:
{skills}

References:
{references}
""".strip()

        data = {
            "id": str(uuid.uuid4()),
            "student_id": uid,
            "title":
                "CV Creation Request",
            "subject":
                "CV Service",
            "description":
                description,
            "status":
                "pending",
            "admin_note":
                "CV_ADMIN_REQUEST",
            "answer_text":
                None
        }

        result, error = db_insert(
            "assignments",
            data
        )

        if error:

            flash(
                "CV request could not be submitted: "
                + str(error)
            )

            return redirect(
                request.url
            )

        flash(
            "Your CV request has been sent to the administrator."
        )

        return redirect(
            url_for("cv")
        )

    content = """

<div class="hero">

<div class="hero-content">

<h1>
Administrator CV Creation
</h1>

<p>
Provide your information and an administrator
can prepare the professional CV for you.
</p>

</div>

</div>

<div class="card">

<form method="POST">

<label>
Full Name
</label>

<input name="name"
       required>

<label>
Phone
</label>

<input name="phone">

<label>
Professional Title
</label>

<input name="title">

<label>
Professional Summary
</label>

<textarea name="summary"></textarea>

<label>
Education
</label>

<textarea name="education"></textarea>

<label>
Work Experience
</label>

<textarea name="experience"></textarea>

<label>
Skills
</label>

<textarea name="skills"></textarea>

<label>
References
</label>

<textarea name="references"></textarea>

<button class="btn-orange">
Send CV Request
</button>

</form>

</div>

"""

    return render_page(
        content,
        "Admin CV Request"
    )


@app.route("/cv")
@login_required
def cv():
    return redirect(
        url_for("cv_builder")
    )


# ============================================================
# ADMIN
# ============================================================

@app.route("/admin")
@admin_required
def admin():

    assignment_rows, _ = db_get(
        "assignments",
        {
            "select": "*",
            "order":
                "created_at.desc"
        }
    )

    driver_rows, _ = db_get(
        "driver_profiles",
        {
            "select": "*",
            "order":
                "created_at.desc"
        }
    )

    delivery_rows, _ = db_get(
        "delivery_requests",
        {
            "select": "*",
            "order":
                "created_at.desc"
        }
    )

    assignment_count = len(
        assignment_rows or []
    )

    driver_count = len(
        driver_rows or []
    )

    delivery_count = len(
        delivery_rows or []
    )

    cv_count = len([
        a for a in
        (assignment_rows or [])
        if
        str(
            a.get("admin_note")
            or ""
        ).startswith(
            "CV_ADMIN_REQUEST"
        )
    ])

    content = f"""

<div class="hero">

<div class="hero-content">

<div class="service-number">
ADMINISTRATION
</div>

<h1>
KOJA AFRICA Admin
</h1>

<p>
Manage the three platform services.
</p>

</div>

</div>

<div class="stat-grid">

<div class="stat">
<strong>
{assignment_count}
</strong>
Assignments
</div>

<div class="stat">
<strong>
{driver_count}
</strong>
Drivers
</div>

<div class="stat">
<strong>
{delivery_count}
</strong>
Deliveries
</div>

<div class="stat">
<strong>
{cv_count}
</strong>
CV Requests
</div>

</div>

<br>

<div class="grid">

<div class="card">

<h2>
Assignments
</h2>

<p class="muted">
Review and answer submitted assignments.
</p>

<a class="btn"
   href="/admin/assignments">
Manage Assignments
</a>

</div>

<div class="card">

<h2>
Drivers
</h2>

<p class="muted">
Approve drivers and manage driver status.
</p>

<a class="btn btn-green"
   href="/admin/drivers">
Manage Drivers
</a>

</div>

<div class="card">

<h2>
Deliveries
</h2>

<p class="muted">
Manage active driver and delivery requests.
</p>

<a class="btn btn-green"
   href="/admin/deliveries">
Manage Deliveries
</a>

</div>

<div class="card">

<h2>
CV Requests
</h2>

<p class="muted">
Review administrator-assisted CV requests.
</p>

<a class="btn btn-orange"
   href="/admin/cv">
Manage CV Requests
</a>

</div>

</div>

"""

    return render_page(
        content,
        "Admin"
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
            "select": "*",
            "order":
                "created_at.desc"
        }
    )

    if error:
        rows = []

    cards = ""

    for assignment in rows or []:

        cards += f"""

<div class="card">

<h3>
{esc(
    assignment.get("title")
)}
</h3>

<p>
Subject:
{esc(
    assignment.get("subject")
)}
</p>

<p>
Student:
{esc(
    assignment.get("student_id")
)}
</p>

<p>
Status:
<span class="status">
{esc(
    assignment.get("status")
)}
</span>
</p>

<a class="btn"
   href="/admin/assignments/{assignment.get("id")}">
Process
</a>

</div>

"""

    content = f"""

<div class="hero">

<div class="hero-content">

<h1>
Assignment Management
</h1>

</div>

</div>

<div class="grid">

{cards or
'''
<div class="card">
No assignments.
</div>
'''}

</div>

"""

    return render_page(
        content,
        "Admin Assignments"
    )


# ============================================================
# ADMIN ASSIGNMENT PROCESS
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

        status = request.form.get(
            "status",
            "in_progress"
        )

        answer_text = request.form.get(
            "answer_text",
            ""
        ).strip()

        note = request.form.get(
            "admin_note",
            ""
        ).strip()

        answer_file = request.files.get(
            "answer_file"
        )

        if (
            answer_file
            and
            answer_file.filename
        ):

            info, upload_error = storage_upload(
                answer_file,
                "assignment-answers"
            )

            if upload_error:

                flash(
                    "Answer file upload failed: "
                    +
                    str(upload_error)
                )

                return redirect(
                    request.url
                )

            note += (
                "\nANSWER_FILE|"
                +
                info["path"]
                +
                "|"
                +
                info["filename"]
                +
                "|"
                +
                info["content_type"]
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

        if status in {
            "completed",
            "approved"
        }:

            data["completed_at"] = (
                now_iso()
            )

        result, update_error = db_update(
            "assignments",
            {
                "id":
                    assignment_id
            },
            data
        )

        flash(
            "Assignment updated."
            if not update_error
            else
            "Assignment update failed."
        )

        return redirect(
            request.url
        )

    content = f"""

<div class="card">

<h2>
{esc(
    assignment.get("title")
)}
</h2>

<p>
Student:
{esc(
    assignment.get("student_id")
)}
</p>

<p>
Subject:
{esc(
    assignment.get("subject")
)}
</p>

<div class="divider"></div>

<h3>
Question
</h3>

<p>
{esc(
    assignment.get("description")
)}
</p>

</div>

<div class="card">

<h2>
Process
</h2>

<form method="POST"
      enctype="multipart/form-data">

<label>
Status
</label>

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

<label>
Admin Note
</label>

<textarea
    name="admin_note"
>{esc(
    assignment.get("admin_note")
)}</textarea>

<label>
Answer
</label>

<textarea
    name="answer_text"
>{esc(
    assignment.get("answer_text")
)}</textarea>

<label>
Answer File
</label>

<input
    type="file"
    name="answer_file"
    accept=".pdf,.doc,.docx"
>

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
# ADMIN DRIVERS
# ============================================================

@app.route("/admin/drivers")
@admin_required
def admin_drivers():

    rows, error = db_get(
        "driver_profiles",
        {
            "select": "*",
            "order":
                "created_at.desc"
        }
    )

    if error:
        rows = []

    cards = ""

    for driver in rows or []:

        cards += f"""

<div class="card">

<h3>
{esc(
    driver.get("vehicle_type")
)}
</h3>

<p>
Vehicle:
{esc(
    driver.get("vehicle_number")
)}
</p>

<p>
License:
{esc(
    driver.get("license_number")
)}
</p>

<p>
Location:
{esc(
    driver.get("location_name")
)}
</p>

<p>
Status:
<span class="status">
{esc(
    driver.get("status")
)}
</span>
</p>

<form method="POST"
      action="/admin/drivers/{driver.get("id")}">

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

<button>
Save
</button>

</form>

</div>

"""

    content = f"""

<div class="hero">

<div class="hero-content">

<h1>
Driver Management
</h1>

</div>

</div>

<div class="grid">

{cards or
'''
<div class="card">
No drivers.
</div>
'''}

</div>

"""

    return render_page(
        content,
        "Admin Drivers"
    )


@app.route(
    "/admin/drivers/<driver_id>",
    methods=["POST"]
)
@admin_required
def admin_driver_update(
    driver_id
):

    status = request.form.get(
        "status",
        "pending"
    )

    result, error = db_update(
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

    flash(
        "Driver updated."
        if not error
        else
        "Driver update failed."
    )

    return redirect(
        url_for("admin_drivers")
    )


# ============================================================
# ADMIN DELIVERIES
# ============================================================

@app.route("/admin/deliveries")
@admin_required
def admin_deliveries():

    rows, error = db_get(
        "delivery_requests",
        {
            "select": "*",
            "order":
                "created_at.desc"
        }
    )

    if error:
        rows = []

    cards = ""

    for delivery in rows or []:

        cards += f"""

<div class="card">

<h3>
Delivery
</h3>

<p>
Pickup:
{esc(
    delivery.get(
        "pickup_location"
    )
)}
</p>

<p>
Destination:
{esc(
    delivery.get(
        "destination_location"
    )
)}
</p>

<p>
Driver:
{esc(
    delivery.get(
        "driver_id"
    )
    or
    "Not assigned"
)}
</p>

<p>
Status:
<span class="status">
{esc(
    delivery.get(
        "status"
    )
)}
</span>
</p>

<form method="POST"
      action="/admin/deliveries/{delivery.get("id")}">

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
Update
</button>

</form>

</div>

"""

    content = f"""

<div class="hero">

<div class="hero-content">

<h1>
Delivery Management
</h1>

</div>

</div>

<div class="grid">

{cards or
'''
<div class="card">
No delivery requests.
</div>
'''}

</div>

"""

    return render_page(
        content,
        "Admin Deliveries"
    )


@app.route(
    "/admin/deliveries/<delivery_id>",
    methods=["POST"]
)
@admin_required
def admin_delivery_update(
    delivery_id
):

    status = request.form.get(
        "status",
        "pending"
    )

    data = {
        "status":
            status,
        "updated_at":
            now_iso()
    }

    if status == "accepted":
        data["accepted_at"] = now_iso()

    elif status == "started":
        data["started_at"] = now_iso()

    elif status == "completed":
        data["completed_at"] = now_iso()

    result, error = db_update(
        "delivery_requests",
        {
            "id":
                delivery_id
        },
        data
    )

    flash(
        "Delivery updated."
        if not error
        else
        "Delivery update failed."
    )

    return redirect(
        url_for("admin_deliveries")
    )


# ============================================================
# ADMIN CV REQUESTS
# ============================================================

@app.route("/admin/cv")
@admin_required
def admin_cv():

    rows, error = db_get(
        "assignments",
        {
            "select": "*",
            "order":
                "created_at.desc"
        }
    )

    if error:
        rows = []

    cv_requests = []

    for assignment in rows or []:

        note = str(
            assignment.get(
                "admin_note"
            )
            or
            ""
        )

        if note.startswith(
            "CV_ADMIN_REQUEST"
        ):

            cv_requests.append(
                assignment
            )

    cards = ""

    for cv in cv_requests:

        cards += f"""

<div class="card">

<h3>
CV Creation Request
</h3>

<p>
Customer:
{esc(
    cv.get("student_id")
)}
</p>

<p>
Status:
<span class="status">
{esc(
    cv.get("status")
)}
</span>
</p>

<div class="divider"></div>

<pre style="
white-space:pre-wrap;
font-family:Arial;
line-height:1.6;
">{esc(
    cv.get("description")
)}</pre>

<form method="POST"
      action="/admin/cv/{cv.get("id")}">

<label>
Administrator Response
</label>

<textarea
    name="answer_text"
    required
>{esc(
    cv.get("answer_text")
)}</textarea>

<label>
Status
</label>

<select name="status">

<option value="in_progress">
In Progress
</option>

<option value="completed">
Completed
</option>

</select>

<button class="btn-orange">
Save CV
</button>

</form>

</div>

"""

    content = f"""

<div class="hero">

<div class="hero-content">

<h1>
CV Requests
</h1>

<p>
Administrator-assisted CV creation.
</p>

</div>

</div>

<div class="grid">

{cards or
'''
<div class="card">
No CV requests.
</div>
'''}

</div>

"""

    return render_page(
        content,
        "Admin CV"
    )


@app.route(
    "/admin/cv/<cv_id>",
    methods=["POST"]
)
@admin_required
def admin_cv_update(cv_id):

    answer_text = request.form.get(
        "answer_text",
        ""
    ).strip()

    status = request.form.get(
        "status",
        "completed"
    )

    result, error = db_update(
        "assignments",
        {
            "id":
                cv_id
        },
        {
            "answer_text":
                answer_text,
            "status":
                status,
            "updated_at":
                now_iso()
        }
    )

    flash(
        "CV request updated."
        if not error
        else
        "CV update failed."
    )

    return redirect(
        url_for("admin_cv")
    )


# ============================================================
# HEALTH
# ============================================================

@app.route("/health")
def health():

    return jsonify({
        "status": "ok",
        "application":
            "KOJA AFRICA",
        "services": [
            "assignments",
            "driver_delivery_live_tracking",
            "cv_services"
        ],
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

<h2>
Page Not Found
</h2>

<p class="muted">
The page you requested does not exist.
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

<h2>
Server Error
</h2>

<p class="muted">
An unexpected server error occurred.
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

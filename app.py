import os
import uuid
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
# SINGLE-FILE PRODUCTION APPLICATION
#
# SERVICES
# 1. ASSIGNMENTS
# 2. DRIVER & DELIVERY + LIVE GPS/MAP
# 3. CV GENERATOR
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
# BASIC FUNCTIONS
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


def current_user():
    return session.get("user")


def logged_in():
    return bool(current_user())


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


def allowed_file(filename):
    if not filename:
        return False

    if "." not in filename:
        return False

    extension = filename.rsplit(
        ".",
        1
    )[1].lower()

    return extension in ALLOWED_EXTENSIONS


def login_required(fn):

    @wraps(fn)
    def wrapper(*args, **kwargs):

        if not logged_in():
            flash(
                "Please log in to continue."
            )
            return redirect(
                url_for("login")
            )

        return fn(*args, **kwargs)

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

        return fn(*args, **kwargs)

    return wrapper


# ============================================================
# SUPABASE
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


def db_get(
    table,
    params=None
):

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
                "GET %s: %s",
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
            "Database GET error"
        )

        return None, str(exc)


def db_insert(
    table,
    data
):

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
                "INSERT %s: %s",
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
            "Database INSERT error"
        )

        return None, str(exc)


def db_update(
    table,
    filters,
    data
):

    if not configuration_ok():
        return None, "Supabase is not configured."

    params = {}

    for key, value in filters.items():

        params[key] = (
            f"eq.{value}"
        )

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

    except Exception as exc:

        logger.exception(
            "Database UPDATE error"
        )

        return None, str(exc)


# ============================================================
# SUPABASE AUTH
# ============================================================

def auth_signup(
    email,
    password
):

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

        return None, str(exc)


def auth_login(
    email,
    password
):

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

        return None, str(exc)


# ============================================================
# STORAGE
# ============================================================

def storage_upload(
    file_storage,
    folder
):

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

        return None, (
            "File is larger than 15 MB."
        )

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
                "STORAGE: %s",
                response.text
            )

            return None, response.text

        return {
            "path": object_name,
            "filename": filename,
            "content_type":
                content_type,
            "size":
                len(content)
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
            f"{SUPABASE_BUCKET}/"
            f"{path}",
            headers=headers,
            timeout=60
        )

        if not response.ok:

            return None, response.text

        return response.content, None

    except Exception as exc:

        return None, str(exc)


# ============================================================
# PAGE TEMPLATE
# ============================================================

PAGE = """
<!DOCTYPE html>
<html lang="en">

<head>

<meta charset="UTF-8">

<meta name="viewport"
      content="width=device-width,
               initial-scale=1.0">

<title>
{{ title }} | KOJA AFRICA
</title>

<link rel="stylesheet"
      href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js">
</script>

<style>

*{
    box-sizing:border-box;
}

html{
    scroll-behavior:smooth;
}

body{
    margin:0;
    padding:0;
    background:#f4f7fb;
    color:#172033;
    font-family:
        Inter,
        Arial,
        Helvetica,
        sans-serif;
}

/* NAVIGATION */

.navbar{
    position:sticky;
    top:0;
    z-index:1000;
    background:
        rgba(15,23,42,.96);
    backdrop-filter:blur(12px);
    border-bottom:
        1px solid rgba(255,255,255,.08);
}

.nav-inner{
    max-width:1180px;
    margin:auto;
    padding:14px 20px;
    display:flex;
    align-items:center;
    justify-content:space-between;
    gap:20px;
}

.logo{
    color:white;
    text-decoration:none;
    font-size:22px;
    font-weight:800;
    letter-spacing:.5px;
}

.nav-links{
    display:flex;
    flex-wrap:wrap;
    gap:6px;
}

.nav-links a{
    color:#dbeafe;
    text-decoration:none;
    padding:9px 12px;
    border-radius:8px;
    font-size:14px;
    transition:.25s ease;
}

.nav-links a:hover{
    background:
        rgba(255,255,255,.1);
    color:white;
}

/* PAGE */

.container{
    width:100%;
    max-width:1180px;
    margin:auto;
    padding:28px 20px 50px;
}

/* ANIMATION */

.animate{
    animation:
        fadeUp .65s ease both;
}

@keyframes fadeUp{
    from{
        opacity:0;
        transform:
            translateY(22px);
    }

    to{
        opacity:1;
        transform:
            translateY(0);
    }
}

@keyframes floatCard{
    0%,100%{
        transform:translateY(0);
    }

    50%{
        transform:
            translateY(-5px);
    }
}

@keyframes pulse{
    0%{
        box-shadow:
            0 0 0 0
            rgba(37,99,235,.4);
    }

    70%{
        box-shadow:
            0 0 0 12px
            rgba(37,99,235,0);
    }

    100%{
        box-shadow:
            0 0 0 0
            rgba(37,99,235,0);
    }
}

/* HERO */

.hero{
    position:relative;
    overflow:hidden;
    padding:48px 36px;
    border-radius:24px;
    margin-bottom:24px;
    color:white;
    background:
        linear-gradient(
            135deg,
            #0f172a,
            #1e3a8a,
            #0f766e
        );
    box-shadow:
        0 18px 45px
        rgba(15,23,42,.18);
    animation:
        fadeUp .7s ease both;
}

.hero:before{
    content:"";
    position:absolute;
    width:250px;
    height:250px;
    border-radius:50%;
    right:-80px;
    top:-100px;
    background:
        rgba(255,255,255,.08);
}

.hero:after{
    content:"";
    position:absolute;
    width:180px;
    height:180px;
    border-radius:50%;
    left:-90px;
    bottom:-100px;
    background:
        rgba(255,255,255,.05);
}

.hero-content{
    position:relative;
    z-index:2;
}

.hero h1{
    font-size:
        clamp(30px,5vw,56px);
    margin:
        0 0 12px;
    line-height:1.05;
}

.hero p{
    max-width:720px;
    font-size:17px;
    line-height:1.7;
    color:#dbeafe;
}

/* SERVICE GRID */

.grid{
    display:grid;
    grid-template-columns:
        repeat(
            auto-fit,
            minmax(270px,1fr)
        );
    gap:20px;
}

/* CARD */

.card{
    background:white;
    border-radius:18px;
    padding:24px;
    margin-bottom:20px;
    border:
        1px solid #e5e7eb;
    box-shadow:
        0 8px 28px
        rgba(15,23,42,.07);
    animation:
        fadeUp .55s ease both;
    transition:
        transform .25s ease,
        box-shadow .25s ease,
        border-color .25s ease;
}

.card:hover{
    transform:
        translateY(-4px);
    box-shadow:
        0 16px 35px
        rgba(15,23,42,.11);
    border-color:
        #cbd5e1;
}

.service-card{
    min-height:250px;
}

.service-card:hover{
    animation:
        floatCard 2s ease-in-out infinite;
}

.service-number{
    width:42px;
    height:42px;
    border-radius:12px;
    display:flex;
    align-items:center;
    justify-content:center;
    background:#eff6ff;
    color:#1d4ed8;
    font-weight:800;
    margin-bottom:18px;
}

.card h2,
.card h3{
    margin-top:0;
    color:#111827;
}

.card p{
    line-height:1.65;
}

/* BUTTONS */

.btn,
button{
    display:inline-block;
    border:0;
    border-radius:10px;
    padding:12px 18px;
    background:#2563eb;
    color:white;
    text-decoration:none;
    cursor:pointer;
    font-size:14px;
    font-weight:700;
    transition:
        transform .2s ease,
        box-shadow .2s ease,
        background .2s ease;
}

.btn:hover,
button:hover{
    transform:
        translateY(-2px);
    box-shadow:
        0 8px 18px
        rgba(37,99,235,.2);
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

/* FORMS */

label{
    display:block;
    margin-bottom:6px;
    font-weight:700;
    font-size:14px;
    color:#374151;
}

input,
textarea,
select{
    width:100%;
    padding:13px 14px;
    margin:
        0 0 17px;
    border:
        1px solid #d1d5db;
    border-radius:10px;
    background:white;
    color:#111827;
    font-size:15px;
    outline:none;
    transition:
        border-color .2s ease,
        box-shadow .2s ease;
}

input:focus,
textarea:focus,
select:focus{
    border-color:#2563eb;
    box-shadow:
        0 0 0 3px
        rgba(37,99,235,.12);
}

textarea{
    min-height:140px;
    resize:vertical;
}

/* STATUS */

.status{
    display:inline-flex;
    align-items:center;
    padding:
        6px 11px;
    border-radius:999px;
    background:#f1f5f9;
    color:#334155;
    font-size:12px;
    font-weight:800;
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

/* FLASH */

.flash{
    padding:14px 17px;
    margin-bottom:15px;
    border-radius:10px;
    background:#eff6ff;
    border:
        1px solid #bfdbfe;
    color:#1e3a8a;
    animation:
        fadeUp .4s ease both;
}

/* MAP */

#map{
    width:100%;
    height:450px;
    border-radius:16px;
    overflow:hidden;
    border:
        1px solid #dbeafe;
}

.map-small{
    height:320px !important;
}

/* TRACKING */

.tracking-status{
    display:flex;
    align-items:center;
    gap:10px;
    padding:13px;
    background:#f8fafc;
    border-radius:10px;
    margin-bottom:14px;
}

.live-dot{
    width:10px;
    height:10px;
    border-radius:50%;
    background:#16a34a;
    animation:
        pulse 1.8s infinite;
}

/* STAT */

.stat{
    padding:18px;
    border-radius:14px;
    background:#f8fafc;
    border:1px solid #e5e7eb;
}

.stat-number{
    font-size:30px;
    font-weight:800;
    color:#1d4ed8;
}

/* TABLE */

.table-wrap{
    overflow-x:auto;
}

table{
    width:100%;
    border-collapse:collapse;
}

th,
td{
    padding:13px;
    border-bottom:
        1px solid #e5e7eb;
    text-align:left;
    font-size:14px;
}

th{
    color:#374151;
    background:#f8fafc;
}

/* FOOTER */

footer{
    background:#0f172a;
    color:#94a3b8;
    text-align:center;
    padding:32px 20px;
    line-height:1.7;
}

/* MOBILE */

@media(max-width:760px){

    .nav-inner{
        align-items:flex-start;
        flex-direction:column;
    }

    .nav-links{
        width:100%;
    }

    .nav-links a{
        font-size:13px;
        padding:8px 9px;
    }

    .container{
        padding:
            20px 14px 40px;
    }

    .hero{
        padding:32px 23px;
        border-radius:18px;
    }

    .card{
        padding:19px;
    }

    #map{
        height:360px;
    }
}

</style>

</head>

<body>

<nav class="navbar">

<div class="nav-inner">

<a class="logo"
   href="/">
KOJA AFRICA
</a>

<div class="nav-links">

<a href="/">
Home
</a>

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

<strong>
KOJA AFRICA
</strong>

<br>

Assignments
&nbsp; | &nbsp;
Driver & Delivery
&nbsp; | &nbsp;
CV Services

<br><br>

Academic assistance, mobility and professional CV creation.

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

<h1>
KOJA AFRICA
</h1>

<p>
A practical digital platform for academic
assignments, driver and delivery services,
and professional CV creation.
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

<div class="service-number">
01
</div>

<h2>
Assignments
</h2>

<p>
Submit assignment questions, upload supporting
files and follow the progress of your request.
Answers can be provided by the KOJA administrator.
</p>

<a class="btn"
   href="/assignments">
Open Assignments
</a>

</div>


<div class="card service-card">

<div class="service-number">
02
</div>

<h2>
Driver & Delivery
</h2>

<p>
Find approved online drivers, request a delivery
and track the driver using live GPS location and
an interactive map.
</p>

<a class="btn btn-green"
   href="/drivers">
Find a Driver
</a>

</div>


<div class="card service-card">

<div class="service-number">
03
</div>

<h2>
CV Services
</h2>

<p>
Create your own professional CV directly on KOJA
or submit your information for administrator
assistance and PDF generation.
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
                "Registration failed: "
                + str(error)
            )

            return redirect(
                url_for("register")
            )

        flash(
            "Account created successfully. "
            "You can now log in."
        )

        return redirect(
            url_for("login")
        )

    content = """

<div class="card animate">

<h2>
Create Account
</h2>

<p>
Create your KOJA AFRICA account using
only your email and password.
</p>

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
    minlength="6"
    required
    autocomplete="new-password"
>

<button type="submit">
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
            "id":
                auth_user.get("id"),
            "email":
                auth_user.get("email")
                or email
        }

        session.permanent = True

        return redirect(
            url_for("dashboard")
        )

    content = """

<div class="card animate">

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

<button type="submit">
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

<h1>
Dashboard
</h1>

<p>
Welcome back.
<br>
{u.get("email", "")}
</p>

</div>

</div>


<div class="grid">


<div class="card service-card">

<div class="service-number">
01
</div>

<h2>
Assignments
</h2>

<p>
Submit and manage academic questions.
</p>

<a class="btn"
   href="/assignments">
Open
</a>

</div>


<div class="card service-card">

<div class="service-number">
02
</div>

<h2>
Driver & Delivery
</h2>

<p>
Request a driver, monitor deliveries
and follow live GPS tracking.
</p>

<a class="btn btn-green"
   href="/drivers">
Open
</a>

</div>


<div class="card service-card">

<div class="service-number">
03
</div>

<h2>
CV
</h2>

<p>
Build your own CV or submit your
information for administrator preparation.
</p>

<a class="btn btn-orange"
   href="/cv">
Open
</a>

</div>


</div>


<div class="grid">

<div class="card">

<h3>
Driver Registration
</h3>

<p>
Register as a driver and wait for
administrator approval.
</p>

<a class="btn btn-green"
   href="/drivers/register">
Register
</a>

</div>


<div class="card">

<h3>
My Deliveries
</h3>

<p>
View active and previous delivery requests.
</p>

<a class="btn"
   href="/deliveries">
View Deliveries
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
            "select":
                "*",
            "order":
                "created_at.desc"
        }
    )

    if error:
        rows = []

        flash(
            "Unable to load assignments."
        )

    cards = ""

    for assignment in rows or []:

        cards += f"""

<div class="card">

<h3>
{assignment.get("title") or "Assignment"}
</h3>

<p>
<strong>
Subject:
</strong>

{assignment.get("subject") or ""}
</p>

<p>
<strong>
Status:
</strong>

<span class="status">
{assignment.get("status") or "pending"}
</span>
</p>

<a class="btn"
   href="/assignments/{assignment.get("id")}">
View
</a>

</div>

"""

    content = f"""

<div class="hero">

<div class="hero-content">

<h1>
Assignments
</h1>

<p>
Submit academic questions and track
your answers.
</p>

<a class="btn"
   href="/assignments/new">
New Assignment
</a>

</div>

</div>

<div class="grid">

{cards or
'<div class="card">No assignments yet.</div>'}

</div>

"""

    return render_page(
        content,
        "Assignments"
    )


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

        file = request.files.get(
            "question_file"
        )

        if not title or not subject or not description:

            flash(
                "Title, subject and question are required."
            )

            return redirect(
                url_for("new_assignment")
            )

        file_info = None

        if file and file.filename:

            file_info, error = storage_upload(
                file,
                "assignment-questions"
            )

            if error:

                flash(
                    "File upload failed: "
                    + str(error)
                )

                return redirect(
                    url_for("new_assignment")
                )

        admin_note = ""

        if file_info:

            admin_note = (
                "QUESTION_FILE|"
                + file_info["path"]
                + "|"
                + file_info["filename"]
                + "|"
                + file_info["content_type"]
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
                url_for("new_assignment")
            )

        flash(
            "Assignment submitted successfully."
        )

        return redirect(
            url_for("assignments")
        )

    content = """

<div class="card animate">

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

<button type="submit">
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

    content = f"""

<div class="card">

<h2>
{assignment.get("title") or ""}
</h2>

<p>
<strong>
Subject:
</strong>

{assignment.get("subject") or ""}
</p>

<p>
<strong>
Status:
</strong>

<span class="status">
{assignment.get("status") or "pending"}
</span>
</p>

<hr>

<h3>
Question
</h3>

<p>
{assignment.get("description") or ""}
</p>

</div>


<div class="card">

<h2>
Answer
</h2>

<p>
{assignment.get("answer_text")
 or
"The administrator has not completed the answer yet."}
</p>

</div>

"""

    return render_page(
        content,
        "Assignment"
    )


# ============================================================
# ADMIN ASSIGNMENTS
# ============================================================

@app.route("/admin")
@admin_required
def admin():

    rows, error = db_get(
        "assignments",
        {
            "select":
                "*",
            "order":
                "created_at.desc"
        }
    )

    cards = ""

    for a in rows or []:

        cards += f"""

<div class="card">

<h3>
{a.get("title") or ""}
</h3>

<p>
Student:
{a.get("student_id") or ""}
</p>

<p>
Subject:
{a.get("subject") or ""}
</p>

<p>
Status:

<span class="status">
{a.get("status") or "pending"}
</span>

</p>

<a class="btn"
   href="/admin/assignments/{a.get("id")}">
Process Assignment
</a>

</div>

"""

    content = f"""

<div class="hero">

<div class="hero-content">

<h1>
Administrator
</h1>

<p>
Manage the three KOJA AFRICA services.
</p>

</div>

</div>


<div class="grid">

<div class="card">

<h3>
Assignments
</h3>

<a class="btn"
   href="/admin/assignments">
Manage Assignments
</a>

</div>

<div class="card">

<h3>
Drivers
</h3>

<a class="btn btn-green"
   href="/admin/drivers">
Manage Drivers
</a>

</div>

<div class="card">

<h3>
Deliveries
</h3>

<a class="btn btn-green"
   href="/admin/deliveries">
Manage Deliveries
</a>

</div>

<div class="card">

<h3>
CV Requests
</h3>

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

    cards = ""

    for a in rows or []:

        cards += f"""

<div class="card">

<h3>
{a.get("title") or ""}
</h3>

<p>
Student:
{a.get("student_id") or ""}
</p>

<p>
Subject:
{a.get("subject") or ""}
</p>

<p>
Status:
<span class="status">
{a.get("status") or "pending"}
</span>
</p>

<a class="btn"
   href="/admin/assignments/{a.get("id")}">
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
'<div class="card">No assignments.</div>'}

</div>

"""

    return render_page(
        content,
        "Assignment Management"
    )


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

        admin_note = request.form.get(
            "admin_note",
            ""
        ).strip()

        answer_file = request.files.get(
            "answer_file"
        )

        if answer_file and answer_file.filename:

            info, upload_error = storage_upload(
                answer_file,
                "assignment-answers"
            )

            if upload_error:

                flash(
                    "Answer file upload failed: "
                    + str(upload_error)
                )

                return redirect(
                    request.url
                )

            admin_note += (
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
                admin_note,

            "answer_text":
                answer_text,

            "updated_at":
                now_iso()
        }

        if status in (
            "completed",
            "approved"
        ):

            data["completed_at"] = now_iso()

        result, update_error = db_update(
            "assignments",
            {
                "id":
                    assignment_id
            },
            data
        )

        if update_error:

            flash(
                "Update failed: "
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
{assignment.get("title") or ""}
</h2>

<p>
<strong>
Subject:
</strong>

{assignment.get("subject") or ""}
</p>

<h3>
Question
</h3>

<p>
{assignment.get("description") or ""}
</p>

</div>


<div class="card">

<h2>
Process Assignment
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

<textarea name="admin_note">
{assignment.get("admin_note") or ""}
</textarea>


<label>
Written Answer
</label>

<textarea name="answer_text">
{assignment.get("answer_text") or ""}
</textarea>


<label>
Answer File
</label>

<input
    type="file"
    name="answer_file"
    accept=".pdf,.doc,.docx"
>


<button type="submit">
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

        data = {
            "id":
                str(uuid.uuid4()),

            "user_id":
                uid,

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
                current_user()["email"],

            "vehicle_type":
                request.form.get(
                    "vehicle_type",
                    ""
                ).strip(),

            "vehicle_number":
                request.form.get(
                    "vehicle_number",
                    ""
                ).strip(),

            "license_number":
                request.form.get(
                    "license_number",
                    ""
                ).strip(),

            "status":
                "pending",

            "is_online":
                False,

            "latitude":
                None,

            "longitude":
                None,

            "location_name":
                "",

            "last_location_update":
                None
        }

        if not data["full_name"]:

            flash(
                "Full name is required."
            )

            return redirect(
                request.url
            )

        if not data["phone"]:

            flash(
                "Phone number is required."
            )

            return redirect(
                request.url
            )

        if not data["vehicle_type"]:

            flash(
                "Vehicle type is required."
            )

            return redirect(
                request.url
            )

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
            url_for("driver_panel")
        )

    content = """

<div class="card animate">

<h2>
Driver Registration
</h2>

<p>
Register your vehicle and wait for administrator
approval before appearing to customers.
</p>

<form method="POST">

<label>
Full Name
</label>

<input
    name="full_name"
    required
>

<label>
Phone Number
</label>

<input
    name="phone"
    required
>

<label>
Vehicle Type
</label>

<select
    name="vehicle_type"
    required
>

<option value="">
Select vehicle
</option>

<option value="Car">
Car
</option>

<option value="Motorcycle">
Motorcycle
</option>

<option value="Van">
Van
</option>

<option value="Truck">
Truck
</option>

</select>

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

<button
    type="submit"
    class="btn-green"
>
Register Driver
</button>

</form>

</div>

"""

    return render_page(
        content,
        "Driver Registration"
    )


# ============================================================
# DRIVER PANEL
# ============================================================

@app.route("/driver")
@login_required
def driver_panel():

    uid = current_user()["id"]

    rows, error = db_get(
        "driver_profiles",
        {
            "user_id":
                f"eq.{uid}",
            "select":
                "*",
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
            "Driver Panel"
        )

    driver = rows[0]

    online = bool(
        driver.get("is_online")
    )

    approved = (
        driver.get("status")
        == "approved"
    )

    content = f"""

<div class="hero">

<div class="hero-content">

<h1>
Driver Panel
</h1>

<p>
Manage your availability and share
your live GPS location with customers.
</p>

</div>

</div>


<div class="card">

<h2>
Driver Status
</h2>

<p>
Approval:

<span class="status">
{driver.get("status") or "pending"}
</span>
</p>

<p>
Current availability:

<span class="status
{'status-online' if online else ''}">
{'ONLINE' if online else 'OFFLINE'}
</span>
</p>

<p>
Vehicle:
{driver.get("vehicle_type") or ""}
</p>

<p>
Vehicle Number:
{driver.get("vehicle_number") or ""}
</p>

</div>


<div class="card">

<h2>
Live GPS
</h2>

<div class="tracking-status">

<span class="live-dot">
</span>

<span id="gpsStatus">
GPS is waiting to start.
</span>

</div>

<button
    onclick="startDriverGPS()"
    class="btn-green"
>
Start Live Location
</button>

<button
    onclick="stopDriverGPS()"
    class="btn-dark"
>
Stop Location
</button>

<div style="height:15px">
</div>

<div id="driverMap"
     class="map-small">
</div>

</div>


<div class="card">

<h2>
Availability
</h2>

<form method="POST"
      action="/driver/status">

<select name="is_online">

<option value="false"
{'selected' if not online else ''}>
Offline
</option>

<option value="true"
{'selected' if online else ''}>
Online
</option>

</select>

<button
    type="submit"
    class="btn-green"
>
Update Availability
</button>

</form>

</div>


<script>

let driverWatchId = null;

let driverMap = null;

let driverMarker = null;


function initDriverMap(){

    driverMap =
        L.map(
            "driverMap"
        ).setView(
            [-12.8000, 28.2000],
            12
        );

    L.tileLayer(
        "https://{{{{s}}}}.tile.openstreetmap.org/{{{{z}}}}/{{{{x}}}}/{{{{y}}}}.png",
        {{
            maxZoom:19,
            attribution:
                "&copy; OpenStreetMap contributors"
        }}
    ).addTo(
        driverMap
    );
}


function updateDriverMap(
    latitude,
    longitude
){

    if(!driverMap){
        initDriverMap();
    }

    const position = [
        latitude,
        longitude
    ];

    if(!driverMarker){

        driverMarker =
            L.marker(
                position
            ).addTo(
                driverMap
            );

        driverMarker.bindPopup(
            "Your live driver location"
        );

    }else{

        driverMarker.setLatLng(
            position
        );
    }

    driverMap.setView(
        position,
        16
    );
}


function sendDriverLocation(
    latitude,
    longitude
){

    const form =
        new FormData();

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
        "Live GPS Location"
    );

    fetch(
        "/driver/location",
        {
            method:"POST",
            body:form
        }
    )
    .then(
        response =>
            response.json()
    )
    .then(
        data => {

            if(
                data.success
            ){

                document.getElementById(
                    "gpsStatus"
                ).textContent =
                    "Live GPS location is active.";

            }else{

                document.getElementById(
                    "gpsStatus"
                ).textContent =
                    data.message ||
                    "GPS update failed.";

            }

        }
    )
    .catch(
        () => {

            document.getElementById(
                "gpsStatus"
            ).textContent =
                "Unable to send GPS location.";

        }
    );
}


function startDriverGPS(){

    if(!navigator.geolocation){

        document.getElementById(
            "gpsStatus"
        ).textContent =
            "This browser does not support GPS.";

        return;
    }

    driverWatchId =
        navigator.geolocation.watchPosition(

            position => {

                const latitude =
                    position.coords.latitude;

                const longitude =
                    position.coords.longitude;

                updateDriverMap(
                    latitude,
                    longitude
                );

                sendDriverLocation(
                    latitude,
                    longitude
                );

            },

            error => {

                document.getElementById(
                    "gpsStatus"
                ).textContent =
                    "GPS permission is required.";

            },

            {
                enableHighAccuracy:true,
                maximumAge:5000,
                timeout:15000
            }
        );

}


function stopDriverGPS(){

    if(
        driverWatchId !== null
    ){

        navigator.geolocation.clearWatch(
            driverWatchId
        );

        driverWatchId = null;

        document.getElementById(
            "gpsStatus"
        ).textContent =
            "Live GPS has been stopped.";
    }
}


window.addEventListener(
    "load",
    initDriverMap
);

</script>

"""

    return render_page(
        content,
        "Driver Panel"
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

    value = request.form.get(
        "is_online",
        "false"
    ).lower()

    online = value == "true"

    rows, error = db_get(
        "driver_profiles",
        {
            "user_id":
                f"eq.{uid}",
            "select":
                "id,status"
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

    if driver.get("status") != "approved":

        flash(
            "Your driver account must be approved before going online."
        )

        return redirect(
            url_for("driver_panel")
        )

    db_update(
        "driver_profiles",
        {
            "id":
                driver["id"]
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
        + (
            "ONLINE."
            if online
            else
            "OFFLINE."
        )
    )

    return redirect(
        url_for("driver_panel")
    )


# ============================================================
# DRIVER LOCATION API
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
            "user_id":
                f"eq.{uid}",
            "select":
                "id,status"
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

    if driver.get("status") != "approved":

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
    ):

        return jsonify({
            "success":
                False,

            "message":
                "Invalid latitude."
        }), 400

    if not (
        -180 <= longitude <= 180
    ):

        return jsonify({
            "success":
                False,

            "message":
                "Invalid longitude."
        }), 400

    location_name = request.form.get(
        "location_name",
        ""
    ).strip()

    result, update_error = db_update(
        "driver_profiles",
        {
            "id":
                driver["id"]
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
        rows = []

        flash(
            "Unable to load available drivers."
        )

    cards = ""

    for driver in rows or []:

        cards += f"""

<div class="card">

<h3>
{driver.get("full_name") or "Driver"}
</h3>

<p>
Vehicle:
<strong>
{driver.get("vehicle_type") or ""}
</strong>
</p>

<p>
Vehicle Number:
{driver.get("vehicle_number") or ""}
</p>

<p>
Current location:
{driver.get("location_name") or "Live GPS"}
</p>

<p>
<span class="status status-online">
ONLINE
</span>
</p>

<a class="btn btn-green"
   href="/delivery/request/{driver.get("id")}">
Request Driver
</a>

</div>

"""

    content = f"""

<div class="hero">

<div class="hero-content">

<h1>
Available Drivers
</h1>

<p>
Only approved drivers who are currently
online are shown.
</p>

<a class="btn btn-green"
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
    "/delivery/request/<driver_id>",
    methods=["GET", "POST"]
)
@login_required
def delivery_request(
    driver_id
):

    driver_rows, driver_error = db_get(
        "driver_profiles",
        {
            "id":
                f"eq.{driver_id}",

            "status":
                "eq.approved",

            "select":
                "*"
        }
    )

    if driver_error or not driver_rows:

        flash(
            "Driver not found."
        )

        return redirect(
            url_for("drivers")
        )

    driver = driver_rows[0]

    if request.method == "POST":

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
                request.url
            )

        data = {
            "id":
                str(uuid.uuid4()),

            "customer_id":
                current_user()["id"],

            "driver_id":
                driver_id,

            "pickup_location":
                pickup,

            "delivery_location":
                destination,

            "destination_location":
                destination,

            "pickup_latitude":
                None,

            "pickup_longitude":
                None,

            "destination_latitude":
                None,

            "destination_longitude":
                None,

            "latitude":
                driver.get("latitude"),

            "longitude":
                driver.get("longitude"),

            "status":
                "pending",

            "notes":
                notes,

            "service_type":
                "delivery",

            "requested_at":
                now_iso()
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
                request.url
            )

        flash(
            "Delivery request submitted successfully."
        )

        return redirect(
            url_for("my_deliveries")
        )

    content = f"""

<div class="card animate">

<h2>
Request Driver
</h2>

<p>
Driver:
<strong>
{driver.get("full_name") or ""}
</strong>
</p>

<p>
Vehicle:
{driver.get("vehicle_type") or ""}
</p>

<p>
Current location:
{driver.get("location_name") or "Live GPS"}
</p>

<form method="POST">

<label>
Pickup Location
</label>

<input
    name="pickup_location"
    placeholder="Enter pickup location"
    required
>

<label>
Destination
</label>

<input
    name="destination_location"
    placeholder="Enter destination"
    required
>

<label>
Instructions
</label>

<textarea
    name="notes"
    placeholder="Additional delivery instructions"
></textarea>

<button
    type="submit"
    class="btn-green"
>
Request Driver
</button>

</form>

</div>

"""

    return render_page(
        content,
        "Request Driver"
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

        status = (
            delivery.get("status")
            or
            "pending"
        )

        cards += f"""

<div class="card">

<h3>
Delivery Request
</h3>

<p>
Pickup:
<strong>
{delivery.get("pickup_location") or ""}
</strong>
</p>

<p>
Destination:
<strong>
{delivery.get("destination_location") or ""}
</strong>
</p>

<p>
Status:

<span class="status">
{status}
</span>

</p>

<a class="btn btn-green"
   href="/delivery/{delivery.get("id")}">
Track Delivery
</a>

</div>

"""

    content = f"""

<div class="hero">

<div class="hero-content">

<h1>
My Deliveries
</h1>

<p>
Track your active driver and view
delivery history.
</p>

</div>

</div>


<div class="grid">

{cards or
'<div class="card">You have no delivery requests.</div>'}

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
    "/delivery/<delivery_id>"
)
@login_required
def track_delivery(
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
        delivery.get("driver_id")
    )

    driver = None

    if driver_id:

        driver_rows, _ = db_get(
            "driver_profiles",
            {
                "id":
                    f"eq.{driver_id}",

                "select":
                    "*"
            }
        )

        if driver_rows:
            driver = driver_rows[0]

    driver_name = (
        driver.get("full_name")
        if driver
        else
        "Waiting for driver"
    )

    content = f"""

<div class="hero">

<div class="hero-content">

<h1>
Live Delivery Tracking
</h1>

<p>
Follow the assigned driver on the live map.
</p>

</div>

</div>


<div class="grid">

<div class="card">

<h3>
Delivery Status
</h3>

<p>

<span id="deliveryStatus"
      class="status">

{delivery.get("status") or "pending"}

</span>

</p>

<p>
Pickup:
<strong>
{delivery.get("pickup_location") or ""}
</strong>
</p>

<p>
Destination:
<strong>
{delivery.get("destination_location") or ""}
</strong>
</p>

</div>


<div class="card">

<h3>
Driver
</h3>

<p id="driverName">
{driver_name}
</p>

<p id="driverLocation">
Waiting for live GPS...
</p>

<div class="tracking-status">

<span class="live-dot">
</span>

<span>
Live tracking
</span>

</div>

</div>

</div>


<div class="card">

<h2>
Live Map
</h2>

<div id="map">
</div>

</div>


<script>

const deliveryId =
    "{{ delivery_id }}";

let map = null;

let driverMarker = null;

let pickupMarker = null;

let destinationMarker = null;


function initMap(){

    map =
        L.map(
            "map"
        ).setView(
            [-12.8000,28.2000],
            12
        );

    L.tileLayer(
        "https://{{{{s}}}}.tile.openstreetmap.org/{{{{z}}}}/{{{{x}}}}/{{{{y}}}}.png",
        {{
            maxZoom:19,
            attribution:
                "&copy; OpenStreetMap contributors"
        }}
    ).addTo(
        map
    );
}


function setDriverMarker(
    latitude,
    longitude
){

    const position = [
        latitude,
        longitude
    ];

    if(!driverMarker){

        driverMarker =
            L.marker(
                position
            ).addTo(
                map
            );

        driverMarker.bindPopup(
            "Driver live location"
        );

    }else{

        driverMarker.setLatLng(
            position
        );
    }

    map.setView(
        position,
        15
    );
}


function loadTracking(){

    fetch(
        "/api/delivery/"
        + deliveryId
        + "/tracking"
    )

    .then(
        response =>
            response.json()
    )

    .then(
        data => {

            if(!data.success){
                return;
            }

            document.getElementById(
                "deliveryStatus"
            ).textContent =
                data.delivery.status;

            document.getElementById(
                "driverName"
            ).textContent =
                data.driver_name ||
                "Waiting for driver";

            if(
                data.latitude !== null &&
                data.longitude !== null
            ){

                setDriverMarker(
                    data.latitude,
                    data.longitude
                );

                document.getElementById(
                    "driverLocation"
                ).textContent =
                    "Live GPS: "
                    +
                    data.latitude.toFixed(6)
                    +
                    ", "
                    +
                    data.longitude.toFixed(6);

            }else{

                document.getElementById(
                    "driverLocation"
                ).textContent =
                    "Waiting for driver GPS...";
            }

        }
    )

    .catch(
        () => {}
    );
}


window.addEventListener(
    "load",
    () => {

        initMap();

        loadTracking();

        setInterval(
            loadTracking,
            5000
        );

    }
);

</script>

"""

    return render_page(
        content,
        "Live Delivery Tracking"
    )


# ============================================================
# TRACKING API
# ============================================================

@app.route(
    "/api/delivery/<delivery_id>/tracking"
)
@login_required
def delivery_tracking_api(
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

        return jsonify({
            "success":
                False,

            "message":
                "Delivery not found."
        }), 404

    delivery = rows[0]

    driver = None

    driver_id = delivery.get(
        "driver_id"
    )

    if driver_id:

        driver_rows, _ = db_get(
            "driver_profiles",
            {
                "id":
                    f"eq.{driver_id}",

                "select":
                    "*"
            }
        )

        if driver_rows:
            driver = driver_rows[0]

    return jsonify({

        "success":
            True,

        "delivery": {
            "id":
                delivery.get("id"),

            "status":
                delivery.get("status"),

            "pickup":
                delivery.get(
                    "pickup_location"
                ),

            "destination":
                delivery.get(
                    "destination_location"
                )
        },

        "driver_name":
            driver.get("full_name")
            if driver
            else None,

        "latitude":
            driver.get("latitude")
            if driver
            else None,

        "longitude":
            driver.get("longitude")
            if driver
            else None,

        "location_name":
            driver.get("location_name")
            if driver
            else None,

        "last_update":
            driver.get(
                "last_location_update"
            )
            if driver
            else None

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

    cards = ""

    for driver in rows or []:

        cards += f"""

<div class="card">

<h3>
{driver.get("full_name") or ""}
</h3>

<p>
Email:
{driver.get("email") or ""}
</p>

<p>
Phone:
{driver.get("phone") or ""}
</p>

<p>
Vehicle:
{driver.get("vehicle_type") or ""}
</p>

<p>
Vehicle Number:
{driver.get("vehicle_number") or ""}
</p>

<p>
License:
{driver.get("license_number") or ""}
</p>

<p>
Status:

<span class="status">
{driver.get("status") or "pending"}
</span>

</p>

<form method="POST"
      action="/admin/drivers/{driver.get("id")}">

<label>
Approval
</label>

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

<button
    type="submit"
    class="btn-green"
>
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
'<div class="card">No drivers.</div>'}

</div>

"""

    return render_page(
        content,
        "Driver Management"
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

    cards = ""

    for delivery in rows or []:

        cards += f"""

<div class="card">

<h3>
Delivery
</h3>

<p>
Customer:
{delivery.get("customer_id") or ""}
</p>

<p>
Driver:
{delivery.get("driver_id") or "Not assigned"}
</p>

<p>
Pickup:
{delivery.get("pickup_location") or ""}
</p>

<p>
Destination:
{delivery.get("destination_location") or ""}
</p>

<p>
Status:
<span class="status">
{delivery.get("status") or "pending"}
</span>
</p>

<form method="POST"
      action="/admin/deliveries/{delivery.get("id")}">

<label>
Status
</label>

<select name="status">

<option value="pending">
Pending
</option>

<option value="assigned">
Assigned
</option>

<option value="accepted">
Accepted
</option>

<option value="picked_up">
Picked Up
</option>

<option value="in_transit">
In Transit
</option>

<option value="delivered">
Delivered
</option>

<option value="cancelled">
Cancelled
</option>

</select>

<button
    type="submit"
    class="btn-green"
>
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
'<div class="card">No delivery requests.</div>'}

</div>

"""

    return render_page(
        content,
        "Delivery Management"
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

    elif status == "picked_up":
        data["picked_up_at"] = now_iso()

    elif status == "in_transit":
        data["started_at"] = now_iso()

    elif status == "delivered":
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
        "Delivery updated successfully."
        if not error
        else
        "Delivery update failed."
    )

    return redirect(
        url_for("admin_deliveries")
    )


# ============================================================
# CV SERVICE
#
# TWO METHODS
# 1. USER CREATES CV
# 2. ADMIN CREATES CV FOR USER
# ============================================================

@app.route("/cv")
@login_required
def cv_home():

    content = """

<div class="hero">

<div class="hero-content">

<h1>
CV Services
</h1>

<p>
Create a professional CV yourself or submit
your information for administrator preparation.
</p>

</div>

</div>


<div class="grid">


<div class="card service-card">

<div class="service-number">
A
</div>

<h2>
Create My CV
</h2>

<p>
Enter your personal details, education,
experience, skills and references. KOJA
will generate a professional PDF CV.
</p>

<a class="btn btn-orange"
   href="/cv/create">
Create My CV
</a>

</div>


<div class="card service-card">

<div class="service-number">
B
</div>

<h2>
Admin CV Service
</h2>

<p>
Submit your CV information to KOJA.
The administrator can review your information
and generate the final CV.
</p>

<a class="btn btn-dark"
   href="/cv/admin-request">
Request Admin CV
</a>

</div>


</div>

"""

    return render_page(
        content,
        "CV Services"
    )


# ============================================================
# CV FORM
# ============================================================

@app.route(
    "/cv/create",
    methods=["GET", "POST"]
)
@login_required
def cv_create():

    if request.method == "POST":

        uid = current_user()["id"]

        data = {

            "id":
                str(uuid.uuid4()),

            "user_id":
                uid,

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
                    current_user()["email"]
                ).strip(),

            "address":
                request.form.get(
                    "address",
                    ""
                ).strip(),

            "professional_summary":
                request.form.get(
                    "professional_summary",
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

            "certificates":
                request.form.get(
                    "certificates",
                    ""
                ).strip(),

            "references":
                request.form.get(
                    "references",
                    ""
                ).strip(),

            "target_job":
                request.form.get(
                    "target_job",
                    ""
                ).strip(),

            "status":
                "self_generated",

            "created_at":
                now_iso(),

            "updated_at":
                now_iso()
        }

        if not data["full_name"]:

            flash(
                "Full name is required."
            )

            return redirect(
                request.url
            )

        if not data["email"]:

            data["email"] = (
                current_user()["email"]
            )

        result, error = db_insert(
            "cv_profiles",
            data
        )

        if error:

            flash(
                "CV could not be saved: "
                + str(error)
            )

            return redirect(
                request.url
            )

        cv_id = (
            result[0].get("id")
            if result
            else
            data["id"]
        )

        return redirect(
            url_for(
                "cv_pdf",
                cv_id=cv_id
            )
        )

    content = """

<div class="card animate">

<h2>
Create Professional CV
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
Phone
</label>

<input
    name="phone"
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
Address
</label>

<input
    name="address"
>

<label>
Target Job
</label>

<input
    name="target_job"
    placeholder="Position you are applying for"
>

<label>
Professional Summary
</label>

<textarea
    name="professional_summary"
    placeholder="Write a short professional profile"
></textarea>

<label>
Education
</label>

<textarea
    name="education"
    placeholder="School, qualification, year"
></textarea>

<label>
Work Experience
</label>

<textarea
    name="experience"
    placeholder="Employer, position, responsibilities and dates"
></textarea>

<label>
Skills
</label>

<textarea
    name="skills"
    placeholder="Communication, computer skills, leadership..."
></textarea>

<label>
Certificates
</label>

<textarea
    name="certificates"
></textarea>

<label>
References
</label>

<textarea
    name="references"
></textarea>

<button
    type="submit"
    class="btn-orange"
>
Generate My CV
</button>

</form>

</div>

"""

    return render_page(
        content,
        "Create CV"
    )


# ============================================================
# ADMIN CV REQUEST
# ============================================================

@app.route(
    "/cv/admin-request",
    methods=["GET", "POST"]
)
@login_required
def cv_admin_request():

    if request.method == "POST":

        uid = current_user()["id"]

        data = {

            "id":
                str(uuid.uuid4()),

            "user_id":
                uid,

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
                current_user()["email"],

            "address":
                request.form.get(
                    "address",
                    ""
                ).strip(),

            "professional_summary":
                request.form.get(
                    "professional_summary",
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

            "certificates":
                request.form.get(
                    "certificates",
                    ""
                ).strip(),

            "references":
                request.form.get(
                    "references",
                    ""
                ).strip(),

            "target_job":
                request.form.get(
                    "target_job",
                    ""
                ).strip(),

            "status":
                "admin_requested",

            "created_at":
                now_iso(),

            "updated_at":
                now_iso()
        }

        if not data["full_name"]:

            flash(
                "Full name is required."
            )

            return redirect(
                request.url
            )

        result, error = db_insert(
            "cv_profiles",
            data
        )

        if error:

            flash(
                "CV request failed: "
                + str(error)
            )

            return redirect(
                request.url
            )

        flash(
            "CV request submitted to the administrator."
        )

        return redirect(
            url_for("cv")
        )

    content = """

<div class="card animate">

<h2>
Request Administrator CV
</h2>

<p>
Provide your information. The administrator
can review it and generate the final CV.
</p>

<form method="POST">

<label>
Full Name
</label>

<input
    name="full_name"
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
Target Job
</label>

<input
    name="target_job"
>

<label>
Professional Summary
</label>

<textarea
    name="professional_summary"
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
Certificates
</label>

<textarea
    name="certificates"
></textarea>

<label>
References
</label>

<textarea
    name="references"
></textarea>

<button
    type="submit"
    class="btn-orange"
>
Submit CV Request
</button>

</form>

</div>

"""

    return render_page(
        content,
        "Admin CV Request"
    )


# ============================================================
# CV PDF GENERATION
# ============================================================

def generate_cv_pdf(cv):

    try:

        from reportlab.lib.pagesizes import A4

        from reportlab.lib import colors

        from reportlab.lib.styles import (
            getSampleStyleSheet,
            ParagraphStyle
        )

        from reportlab.lib.enums import (
            TA_LEFT,
            TA_CENTER
        )

        from reportlab.platypus import (
            SimpleDocTemplate,
            Paragraph,
            Spacer,
            Table,
            TableStyle,
            KeepTogether
        )

    except Exception as exc:

        raise RuntimeError(
            "ReportLab is required for CV PDF generation."
        ) from exc

    buffer = BytesIO()

    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=42,
        leftMargin=42,
        topMargin=42,
        bottomMargin=42
    )

    styles = getSampleStyleSheet()

    name_style = ParagraphStyle(
        "CVName",
        parent=styles["Title"],
        fontSize=24,
        leading=28,
        alignment=TA_CENTER,
        spaceAfter=7
    )

    contact_style = ParagraphStyle(
        "Contact",
        parent=styles["Normal"],
        fontSize=9,
        leading=13,
        alignment=TA_CENTER,
        spaceAfter=18
    )

    section_style = ParagraphStyle(
        "Section",
        parent=styles["Heading2"],
        fontSize=12,
        leading=15,
        spaceBefore=12,
        spaceAfter=7,
        textColor=colors.HexColor(
            "#1e3a8a"
        )
    )

    body_style = ParagraphStyle(
        "Body",
        parent=styles["BodyText"],
        fontSize=9.5,
        leading=14,
        spaceAfter=5
    )

    story = []

    full_name = (
        cv.get("full_name")
        or
        "Professional CV"
    )

    story.append(
        Paragraph(
            full_name,
            name_style
        )
    )

    contact_parts = []

    if cv.get("phone"):
        contact_parts.append(
            cv["phone"]
        )

    if cv.get("email"):
        contact_parts.append(
            cv["email"]
        )

    if cv.get("address"):
        contact_parts.append(
            cv["address"]
        )

    story.append(
        Paragraph(
            " | ".join(contact_parts),
            contact_style
        )
    )

    if cv.get("target_job"):

        story.append(
            Paragraph(
                cv["target_job"],
                ParagraphStyle(
                    "Target",
                    parent=section_style,
                    alignment=TA_CENTER
                )
            )
        )

    sections = [

        (
            "PROFESSIONAL SUMMARY",
            cv.get(
                "professional_summary"
            )
        ),

        (
            "EDUCATION",
            cv.get(
                "education"
            )
        ),

        (
            "WORK EXPERIENCE",
            cv.get(
                "experience"
            )
        ),

        (
            "SKILLS",
            cv.get(
                "skills"
            )
        ),

        (
            "CERTIFICATES",
            cv.get(
                "certificates"
            )
        ),

        (
            "REFERENCES",
            cv.get(
                "references"
            )
        )
    ]

    for title, text in sections:

        if not text:
            continue

        story.append(
            Paragraph(
                title,
                section_style
            )
        )

        clean_text = (
            str(text)
            .replace(
                "\n",
                "<br/>"
            )
        )

        story.append(
            Paragraph(
                clean_text,
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
                alignment=TA_CENTER,
                textColor=colors.grey
            )
        )
    )

    document.build(
        story
    )

    buffer.seek(0)

    return buffer


@app.route(
    "/cv/<cv_id>/pdf"
)
@login_required
def cv_pdf(cv_id):

    params = {
        "id":
            f"eq.{cv_id}",

        "select":
            "*"
    }

    if not is_admin():

        params["user_id"] = (
            f"eq.{current_user()['id']}"
        )

    rows, error = db_get(
        "cv_profiles",
        params
    )

    if error or not rows:

        flash(
            "CV not found."
        )

        return redirect(
            url_for("cv")
        )

    cv = rows[0]

    try:

        pdf = generate_cv_pdf(
            cv
        )

    except Exception as exc:

        logger.exception(
            "CV PDF generation error"
        )

        flash(
            "Unable to generate CV PDF: "
            + str(exc)
        )

        return redirect(
            url_for("cv")
        )

    return send_file(
        pdf,
        mimetype="application/pdf",
        download_name=(
            secure_filename(
                cv.get("full_name")
                or
                "KOJA_CV"
            )
            + "_CV.pdf"
        ),
        as_attachment=True
    )


# ============================================================
# ADMIN CV MANAGEMENT
# ============================================================

@app.route("/admin/cv")
@admin_required
def admin_cv():

    rows, error = db_get(
        "cv_profiles",
        {
            "select":
                "*",

            "order":
                "created_at.desc"
        }
    )

    cards = ""

    for cv in rows or []:

        cards += f"""

<div class="card">

<h3>
{cv.get("full_name") or ""}
</h3>

<p>
Email:
{cv.get("email") or ""}
</p>

<p>
Target job:
{cv.get("target_job") or ""}
</p>

<p>
Status:

<span class="status">
{cv.get("status") or ""}
</span>

</p>

<a class="btn btn-orange"
   href="/admin/cv/{cv.get("id")}">
Open CV
</a>

<a class="btn btn-dark"
   href="/cv/{cv.get("id")}/pdf">
Generate PDF
</a>

</div>

"""

    content = f"""

<div class="hero">

<div class="hero-content">

<h1>
CV Management
</h1>

<p>
Review CV requests and generate professional
CV documents for users.
</p>

</div>

</div>


<div class="grid">

{cards or
'<div class="card">No CV requests.</div>'}

</div>

"""

    return render_page(
        content,
        "CV Management"
    )


@app.route(
    "/admin/cv/<cv_id>",
    methods=["GET", "POST"]
)
@admin_required
def admin_cv_detail(cv_id):

    rows, error = db_get(
        "cv_profiles",
        {
            "id":
                f"eq.{cv_id}",

            "select":
                "*"
        }
    )

    if error or not rows:

        flash(
            "CV not found."
        )

        return redirect(
            url_for("admin_cv")
        )

    cv = rows[0]

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

            "address":
                request.form.get(
                    "address",
                    ""
                ).strip(),

            "target_job":
                request.form.get(
                    "target_job",
                    ""
                ).strip(),

            "professional_summary":
                request.form.get(
                    "professional_summary",
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

            "certificates":
                request.form.get(
                    "certificates",
                    ""
                ).strip(),

            "references":
                request.form.get(
                    "references",
                    ""
                ).strip(),

            "status":
                "admin_completed",

            "updated_at":
                now_iso()
        }

        result, update_error = db_update(
            "cv_profiles",
            {
                "id":
                    cv_id
            },
            data
        )

        if update_error:

            flash(
                "CV update failed: "
                + str(update_error)
            )

        else:

            flash(
                "CV updated successfully."
            )

        return redirect(
            url_for(
                "admin_cv_detail",
                cv_id=cv_id
            )
        )

    content = f"""

<div class="card">

<h2>
Administrator CV Editor
</h2>

<form method="POST">

<label>
Full Name
</label>

<input
    name="full_name"
    value="{cv.get("full_name") or ""}"
    required
>

<label>
Phone
</label>

<input
    name="phone"
    value="{cv.get("phone") or ""}"
>

<label>
Address
</label>

<input
    name="address"
    value="{cv.get("address") or ""}"
>

<label>
Target Job
</label>

<input
    name="target_job"
    value="{cv.get("target_job") or ""}"
>

<label>
Professional Summary
</label>

<textarea
    name="professional_summary"
>{cv.get("professional_summary") or ""}</textarea>

<label>
Education
</label>

<textarea
    name="education"
>{cv.get("education") or ""}</textarea>

<label>
Work Experience
</label>

<textarea
    name="experience"
>{cv.get("experience") or ""}</textarea>

<label>
Skills
</label>

<textarea
    name="skills"
>{cv.get("skills") or ""}</textarea>

<label>
Certificates
</label>

<textarea
    name="certificates"
>{cv.get("certificates") or ""}</textarea>

<label>
References
</label>

<textarea
    name="references"
>{cv.get("references") or ""}</textarea>

<button
    type="submit"
    class="btn-orange"
>
Save & Complete CV
</button>

<a class="btn btn-dark"
   href="/cv/{cv_id}/pdf">
Generate PDF
</a>

</form>

</div>

"""

    return render_page(
        content,
        "CV Editor"
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

            "driver_delivery_live_tracking",

            "cv_generation"
        ],

        "database_configured":
            configuration_ok()

    })


# ============================================================
# 404
# ============================================================

@app.errorhandler(404)
def error_404(error):

    return render_page(
        """

<div class="card">

<h2>
Page Not Found
</h2>

<p>
The page you requested does not exist.
</p>

<a class="btn"
   href="/">
Return Home
</a>

</div>

""",
        "Page Not Found"
    ), 404


# ============================================================
# 500
# ============================================================

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

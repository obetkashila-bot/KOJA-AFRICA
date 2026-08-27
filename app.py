import os
import uuid
import requests
from functools import wraps
from datetime import datetime, timezone

from flask import (
    Flask,
    request,
    redirect,
    url_for,
    session,
    render_template_string,
    flash,
    abort,
    make_response,
    send_file
)

# ============================================================
# KOJA AFRICA
# KNOWLEDGE • QUESTIONS • ANSWERS
#
# SUPABASE + FLASK
# SINGLE FILE
#
# Database:
#   Supabase PostgreSQL
#
# Authentication:
#   Supabase Auth
#
# Storage:
#   Supabase Storage
#
# ============================================================

app = Flask(__name__)

app.secret_key = os.environ.get(
    "FLASK_SECRET_KEY",
    "CHANGE_THIS_SECRET_KEY"
)

# ============================================================
# SUPABASE CONFIGURATION
# ============================================================

SUPABASE_URL = os.environ.get(
    "SUPABASE_URL",
    ""
).rstrip("/")

SUPABASE_SERVICE_KEY = os.environ.get(
    "SUPABASE_SERVICE_KEY",
    ""
)

SUPABASE_ANON_KEY = os.environ.get(
    "SUPABASE_ANON_KEY",
    SUPABASE_SERVICE_KEY
)

# Storage bucket
STORAGE_BUCKET = os.environ.get(
    "SUPABASE_STORAGE_BUCKET",
    "koja-assignments"
)

# Optional admin email
ADMIN_EMAIL = os.environ.get(
    "KOJA_ADMIN_EMAIL",
    "admin@koja.africa"
).strip().lower()

# Maximum upload
MAX_FILE_SIZE = 15 * 1024 * 1024

ALLOWED_EXTENSIONS = {
    "pdf",
    "doc",
    "docx",
    "txt",
    "jpg",
    "jpeg",
    "png",
    "xls",
    "xlsx",
    "ppt",
    "pptx",
    "csv"
}


# ============================================================
# CHECK CONFIGURATION
# ============================================================

def supabase_configured():
    return bool(
        SUPABASE_URL and
        SUPABASE_SERVICE_KEY
    )


def require_supabase():
    if not supabase_configured():
        raise RuntimeError(
            "Supabase is not configured. "
            "Set SUPABASE_URL and SUPABASE_SERVICE_KEY."
        )


# ============================================================
# SUPABASE HEADERS
# ============================================================

def service_headers():
    require_supabase()

    return {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json"
    }


def auth_headers(access_token=None):
    require_supabase()

    token = access_token or SUPABASE_ANON_KEY

    return {
        "apikey": SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }


# ============================================================
# SUPABASE REST HELPERS
# ============================================================

def supabase_get(table, params=None):
    url = f"{SUPABASE_URL}/rest/v1/{table}"

    response = requests.get(
        url,
        headers=service_headers(),
        params=params or {},
        timeout=30
    )

    if not response.ok:
        raise RuntimeError(
            f"Supabase GET {table} failed: "
            f"{response.status_code} {response.text}"
        )

    return response.json()


def supabase_insert(table, data):
    url = f"{SUPABASE_URL}/rest/v1/{table}"

    headers = service_headers()
    headers["Prefer"] = "return=representation"

    response = requests.post(
        url,
        headers=headers,
        json=data,
        timeout=30
    )

    if not response.ok:
        raise RuntimeError(
            f"Supabase INSERT {table} failed: "
            f"{response.status_code} {response.text}"
        )

    return response.json()


def supabase_update(table, data, params):
    url = f"{SUPABASE_URL}/rest/v1/{table}"

    headers = service_headers()
    headers["Prefer"] = "return=representation"

    response = requests.patch(
        url,
        headers=headers,
        params=params,
        json=data,
        timeout=30
    )

    if not response.ok:
        raise RuntimeError(
            f"Supabase UPDATE {table} failed: "
            f"{response.status_code} {response.text}"
        )

    return response.json()


def supabase_delete(table, params):
    url = f"{SUPABASE_URL}/rest/v1/{table}"

    response = requests.delete(
        url,
        headers=service_headers(),
        params=params,
        timeout=30
    )

    if not response.ok:
        raise RuntimeError(
            f"Supabase DELETE {table} failed: "
            f"{response.status_code} {response.text}"
        )

    return True


# ============================================================
# SUPABASE AUTH
# ============================================================

def supabase_signup(email, password):
    require_supabase()

    url = f"{SUPABASE_URL}/auth/v1/signup"

    response = requests.post(
        url,
        headers=auth_headers(),
        json={
            "email": email,
            "password": password
        },
        timeout=30
    )

    return response


def supabase_login(email, password):
    require_supabase()

    url = f"{SUPABASE_URL}/auth/v1/token"

    response = requests.post(
        url,
        params={
            "grant_type": "password"
        },
        headers=auth_headers(),
        json={
            "email": email,
            "password": password
        },
        timeout=30
    )

    return response


def supabase_logout(access_token):
    if not access_token:
        return

    try:
        requests.post(
            f"{SUPABASE_URL}/auth/v1/logout",
            headers=auth_headers(access_token),
            timeout=15
        )
    except Exception:
        pass


# ============================================================
# PROFILE HELPERS
# ============================================================

def get_profile(user_id):
    rows = supabase_get(
        "profiles",
        {
            "id": f"eq.{user_id}",
            "select": "*",
            "limit": "1"
        }
    )

    return rows[0] if rows else None


def get_profile_by_email(email):
    rows = supabase_get(
        "profiles",
        {
            "email": f"eq.{email}",
            "select": "*",
            "limit": "1"
        }
    )

    return rows[0] if rows else None


def create_profile(user_id, name, email, role="student"):
    existing = get_profile(user_id)

    if existing:
        return existing

    rows = supabase_insert(
        "profiles",
        {
            "id": user_id,
            "name": name,
            "email": email,
            "role": role
        }
    )

    return rows[0] if rows else None


def ensure_profile_for_auth_user(user_id, name, email):
    profile = get_profile(user_id)

    if profile:
        return profile

    # New accounts are always students.
    # Admin promotion should happen separately.
    return create_profile(
        user_id,
        name,
        email,
        "student"
    )


# ============================================================
# CURRENT USER
# ============================================================

def current_user():
    user_id = session.get("user_id")

    if not user_id:
        return None

    try:
        return get_profile(user_id)
    except Exception:
        return None


def login_required(view):

    @wraps(view)
    def wrapper(*args, **kwargs):

        if not current_user():
            flash(
                "Please log in first.",
                "error"
            )
            return redirect(
                url_for("login")
            )

        return view(*args, **kwargs)

    return wrapper


def admin_required(view):

    @wraps(view)
    def wrapper(*args, **kwargs):

        user = current_user()

        if not user:
            flash(
                "Please log in first.",
                "error"
            )
            return redirect(
                url_for("login")
            )

        if user.get("role") != "admin":
            abort(403)

        return view(*args, **kwargs)

    return wrapper


# ============================================================
# GENERAL HELPERS
# ============================================================

def esc(value):
    if value is None:
        return ""

    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def now_iso():
    return datetime.now(
        timezone.utc
    ).isoformat()


def allowed_file(filename):
    if not filename or "." not in filename:
        return False

    extension = filename.rsplit(
        ".",
        1
    )[1].lower()

    return extension in ALLOWED_EXTENSIONS


def clean_filename(filename):
    filename = os.path.basename(
        filename or ""
    )

    filename = filename.replace(
        "\x00",
        ""
    )

    return filename[:200]


def size_text(size):
    try:
        size = int(size)
    except Exception:
        return ""

    if size < 1024:
        return f"{size} B"

    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"

    return f"{size / (1024 * 1024):.1f} MB"


# ============================================================
# LOGGING
# ============================================================

def log_event(
    event,
    category="System",
    level="INFO",
    details=""
):
    try:
        supabase_insert(
            "logs",
            {
                "event": event,
                "category": category,
                "level": level,
                "details": details,
                "user_id": session.get("user_id")
            }
        )
    except Exception as exc:
        print(
            "LOG ERROR:",
            exc
        )


# ============================================================
# STORAGE
# ============================================================

def storage_upload(file, folder):
    require_supabase()

    if not file or not file.filename:
        return None

    original_name = clean_filename(
        file.filename
    )

    if not allowed_file(original_name):
        raise ValueError(
            "This file type is not allowed."
        )

    data = file.read()

    if len(data) > MAX_FILE_SIZE:
        raise ValueError(
            "Maximum file size is 15 MB."
        )

    extension = ""

    if "." in original_name:
        extension = (
            original_name
            .rsplit(".", 1)[1]
            .lower()
        )

    stored_name = (
        f"{uuid.uuid4().hex}"
        f".{extension}"
        if extension
        else uuid.uuid4().hex
    )

    storage_path = (
        f"{folder}/{stored_name}"
    )

    content_type = (
        file.content_type
        or "application/octet-stream"
    )

    url = (
        f"{SUPABASE_URL}/storage/v1/object/"
        f"{STORAGE_BUCKET}/"
        f"{storage_path}"
    )

    headers = {
        "Authorization":
            f"Bearer {SUPABASE_SERVICE_KEY}",
        "apikey":
            SUPABASE_SERVICE_KEY,
        "Content-Type":
            content_type,
        "x-upsert":
            "false"
    }

    response = requests.post(
        url,
        headers=headers,
        data=data,
        timeout=60
    )

    if not response.ok:
        raise RuntimeError(
            "Storage upload failed: "
            f"{response.status_code} "
            f"{response.text}"
        )

    return {
        "original_name": original_name,
        "storage_path": storage_path,
        "size": len(data),
        "content_type": content_type
    }


def storage_download(storage_path):
    require_supabase()

    url = (
        f"{SUPABASE_URL}/storage/v1/object/"
        f"{STORAGE_BUCKET}/"
        f"{storage_path}"
    )

    response = requests.get(
        url,
        headers={
            "Authorization":
                f"Bearer {SUPABASE_SERVICE_KEY}",
            "apikey":
                SUPABASE_SERVICE_KEY
        },
        timeout=60
    )

    if not response.ok:
        return None

    return response


def storage_delete(storage_path):
    require_supabase()

    url = (
        f"{SUPABASE_URL}/storage/v1/object/"
        f"{STORAGE_BUCKET}"
    )

    response = requests.delete(
        url,
        headers={
            "Authorization":
                f"Bearer {SUPABASE_SERVICE_KEY}",
            "apikey":
                SUPABASE_SERVICE_KEY,
            "Content-Type":
                "application/json"
        },
        json={
            "prefixes": [
                storage_path
            ]
        },
        timeout=30
    )

    return response.ok


# ============================================================
# CSS
# ============================================================

CSS = r"""
<style>

:root{
--navy:#07142f;
--navy2:#0e1c40;
--panel:#172653;
--panel2:#202e5c;
--line:rgba(255,255,255,.10);
--text:#f4f6ff;
--muted:#adb7d8;
--blue:#5968ff;
--green:#70df55;
--cyan:#18c7ed;
--orange:#ff8b18;
--pink:#ff3d78;
--purple:#743fc1;
}

*{
box-sizing:border-box
}

html,body{
margin:0;
min-height:100%;
font-family:Arial,Helvetica,sans-serif
}

body{
color:var(--text);
background:
radial-gradient(
circle at 80% 10%,
rgba(84,96,206,.25),
transparent 30%
),
linear-gradient(
145deg,
#07142f,
#121d43 48%,
#2a285b
)
}

a{
text-decoration:none;
color:inherit
}

button,input,textarea,select{
font:inherit
}

.topbar{
position:sticky;
top:0;
z-index:100;
background:rgba(5,17,43,.97);
border-bottom:1px solid var(--line);
backdrop-filter:blur(14px)
}

.topbar-inner{
max-width:1450px;
margin:auto;
min-height:82px;
padding:10px 22px;
display:flex;
align-items:center;
gap:18px
}

.brand{
display:flex;
align-items:center;
min-width:210px
}

.logo{
font-size:43px;
font-weight:900;
letter-spacing:-5px;
line-height:.8
}

.k{color:#29aff6}
.o{color:#65d84e}
.j{color:#ff3f51}
.a{color:#4c72df}

.africa{
text-align:center;
font-size:8px;
letter-spacing:5px;
color:#d4d9ef;
margin-top:8px
}

.search{
flex:1;
max-width:520px;
position:relative
}

.search input{
width:100%;
background:#101c3d;
color:white;
border:1px solid rgba(255,255,255,.06);
border-radius:16px;
padding:15px 18px 15px 50px;
outline:none
}

.search-icon{
position:absolute;
left:17px;
top:50%;
transform:translateY(-50%);
font-size:26px;
color:#aeb8d8
}

.profile{
margin-left:auto;
width:50px;
height:50px;
border-radius:50%;
display:flex;
align-items:center;
justify-content:center;
background:#d7b38e;
color:#563e32;
font-weight:900;
border:3px solid rgba(255,255,255,.3);
position:relative
}

.online{
position:absolute;
right:-1px;
bottom:1px;
width:13px;
height:13px;
border-radius:50%;
background:#62e644;
border:2px solid #10204a
}

.nav{
display:flex;
gap:4px;
align-items:center
}

.nav a{
padding:10px 10px;
border-radius:9px;
color:#cbd3ef;
font-weight:700;
font-size:14px
}

.nav a:hover{
background:rgba(255,255,255,.08);
color:white
}

.menu{
display:none;
border:0;
background:none;
color:#b8c1df;
font-size:30px
}

.container{
max-width:1450px;
margin:auto;
padding:28px 24px 75px
}

.card{
background:
linear-gradient(
145deg,
rgba(27,42,88,.96),
rgba(20,31,68,.97)
);
border:1px solid var(--line);
border-radius:20px;
padding:24px;
margin-bottom:20px;
box-shadow:
0 18px 45px rgba(0,0,0,.18)
}

.hero{
min-height:540px;
position:relative;
overflow:hidden;
padding:38px 44px;
background:
radial-gradient(
circle at 82% 35%,
rgba(91,104,255,.24),
transparent 33%
),
linear-gradient(
135deg,
#172857,
#292a63
)
}

.greeting{
display:inline-block;
padding:10px 19px;
border-radius:25px;
background:
linear-gradient(
90deg,
#3e4aa2,
#5364d3
);
color:#dce1ff;
font-weight:800
}

.hero h1{
font-size:clamp(42px,5vw,67px);
margin:25px 0 12px;
letter-spacing:-2px
}

.hero h1 span{
color:#6371ff
}

.hero p{
max-width:650px;
color:#b7bfda;
font-size:19px;
line-height:1.65;
margin:0
}

.actions{
display:flex;
gap:13px;
flex-wrap:wrap;
margin-top:32px;
position:relative;
z-index:5
}

.btn,.btn2{
display:inline-flex;
align-items:center;
justify-content:center;
gap:8px;
padding:14px 21px;
border-radius:15px;
font-weight:800;
border:0;
cursor:pointer;
transition:.2s
}

.btn:hover,.btn2:hover{
transform:translateY(-2px)
}

.btn{
background:
linear-gradient(
135deg,
#5b6aff,
#6554ff
);
color:#fff;
box-shadow:
0 12px 30px rgba(83,91,255,.25)
}

.btn2{
background:rgba(255,255,255,.04);
border:1px solid var(--line);
color:#dbe0f7
}

.btn.green{
background:rgba(67,146,60,.28);
color:#9af072
}

.btn.orange{
background:rgba(255,139,24,.2);
color:#ffb35d
}

.btn.red{
background:#b52e4c
}

.stats{
display:grid;
grid-template-columns:repeat(4,1fr);
margin-top:42px;
border:1px solid var(--line);
border-radius:19px;
overflow:hidden;
background:rgba(7,18,44,.25);
position:relative;
z-index:5
}

.stat{
text-align:center;
padding:21px 12px;
border-right:1px solid var(--line)
}

.stat:last-child{
border-right:0
}

.stat-icon{
width:51px;
height:51px;
margin:auto auto 9px;
border-radius:50%;
display:flex;
align-items:center;
justify-content:center;
font-size:25px;
font-weight:900;
background:#276bd4
}

.stat:nth-child(2) .stat-icon{
background:#4b9143
}

.stat:nth-child(3) .stat-icon{
background:#6b3fc0
}

.stat:nth-child(4) .stat-icon{
background:#cb6e13
}

.stat h2{
font-size:31px;
margin:0 0 4px
}

.stat p{
margin:0;
color:#aeb8d8;
line-height:1.35
}

.section-title{
display:flex;
justify-content:space-between;
align-items:center;
margin:25px 3px 14px
}

.section-title h2{
margin:0;
font-size:25px
}

.quick-grid{
display:grid;
grid-template-columns:repeat(3,1fr);
gap:16px
}

.quick{
min-height:165px;
padding:21px;
border-radius:18px;
background:rgba(29,43,84,.82);
border:1px solid var(--line);
transition:.2s
}

.quick:hover{
transform:translateY(-3px);
background:rgba(38,54,102,.95)
}

.quick-icon{
width:52px;
height:52px;
border-radius:13px;
display:flex;
align-items:center;
justify-content:center;
font-size:25px;
margin-bottom:16px;
background:#5c49ef
}

.quick:nth-child(2) .quick-icon{
background:#1675d2
}

.quick:nth-child(3) .quick-icon{
background:#4aa23d
}

.quick:nth-child(4) .quick-icon{
background:#e77908
}

.quick:nth-child(5) .quick-icon{
background:#ed3970
}

.quick:nth-child(6) .quick-icon{
background:#743dbc
}

.quick h3{
margin:0 0 7px;
font-size:18px
}

.quick p{
margin:0;
color:#aeb8d8;
line-height:1.45
}

.form-control{
width:100%;
padding:14px 15px;
margin:7px 0 15px;
border-radius:11px;
border:1px solid #34466f;
background:#0e1b3d;
color:white;
outline:none
}

textarea.form-control{
min-height:180px;
resize:vertical
}

label{
display:block;
font-weight:800;
color:#dde2f7;
margin-top:10px
}

.question,.answer{
white-space:pre-wrap;
padding:18px;
border-radius:13px;
line-height:1.7
}

.question{
background:#101d40;
border:1px solid var(--line)
}

.answer{
background:#102b40;
border:1px solid rgba(24,199,237,.16)
}

.document-box{
padding:16px;
border-radius:12px;
background:#101d40;
border:1px solid var(--line);
margin-top:12px
}

.badge{
display:inline-block;
padding:6px 10px;
border-radius:30px;
font-size:12px;
font-weight:800
}

.pending{
background:#55451d;
color:#ffd86a
}

.answered{
background:#1f5330;
color:#9af19c
}

.table-wrap{
overflow:auto
}

table{
width:100%;
border-collapse:collapse;
min-width:700px
}

th,td{
padding:13px;
border-bottom:1px solid var(--line);
text-align:left;
vertical-align:top
}

th{
color:#e0e4f8
}

td{
color:#b8c1dd
}

.muted{
color:#9fa9ca
}

.empty{
text-align:center;
padding:35px;
color:#9fa9ca
}

.alert{
max-width:1000px;
margin:14px auto;
padding:13px 18px;
border-radius:12px;
background:#1d3969
}

.alert.error{
background:#57283a;
color:#ffd9e2
}

.alert.success{
background:#1d5138;
color:#caffd8
}

.auth{
max-width:560px;
margin:45px auto
}

footer{
text-align:center;
color:#8994b6;
padding:30px
}

.mobile-bottom{
display:none
}

@media(max-width:1100px){

.nav{
display:none
}

.menu{
display:block
}

.brand{
min-width:auto
}

.quick-grid{
grid-template-columns:repeat(2,1fr)
}

}

@media(max-width:760px){

.topbar-inner{
min-height:75px;
padding:9px 13px;
gap:10px;
flex-wrap:wrap
}

.brand{
order:2
}

.logo{
font-size:36px
}

.profile{
order:3;
width:44px;
height:44px
}

.menu{
order:1
}

.search{
order:4;
flex-basis:100%;
max-width:none
}

.container{
padding:18px 12px 90px
}

.hero{
min-height:600px;
padding:24px 19px
}

.hero h1{
font-size:42px
}

.hero p{
font-size:16px
}

.actions{
margin-top:25px
}

.actions .btn,
.actions .btn2{
flex:1;
min-width:140px
}

.stats{
grid-template-columns:repeat(2,1fr);
margin-top:30px
}

.stat{
border-bottom:1px solid var(--line)
}

.stat:nth-child(2),
.stat:nth-child(4){
border-right:0
}

.quick-grid{
grid-template-columns:1fr 1fr;
gap:11px
}

.quick{
min-height:145px;
padding:16px
}

.quick h3{
font-size:16px
}

.quick p{
font-size:13px
}

.card{
padding:18px
}

.mobile-bottom{
position:fixed;
left:0;
right:0;
bottom:0;
height:68px;
z-index:90;
display:flex;
align-items:center;
justify-content:space-around;
background:rgba(8,20,49,.98);
border-top:1px solid var(--line)
}

.mobile-bottom a{
text-align:center;
color:#adb7d7;
font-size:12px
}

.mobile-bottom strong{
display:block;
color:#6071ff;
font-size:22px;
line-height:25px
}

}

</style>
"""


# ============================================================
# LAYOUTS
# ============================================================

PUBLIC_LAYOUT = r"""
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport"
      content="width=device-width,initial-scale=1">

<meta name="robots"
      content="index,follow">

<title>{{ title }} | KOJA AFRICA</title>

""" + CSS + r"""
</head>

<body>

<header class="topbar">

<div class="topbar-inner">

<a class="brand" href="/">

<div>

<div class="logo">
<span class="k">k</span>
<span class="o">o</span>
<span class="j">j</span>
<span class="a">a</span>
</div>

<div class="africa">
AFRICA
</div>

</div>

</a>

<nav class="nav"
     style="margin-left:auto">

<a href="/login">
Log In
</a>

<a class="btn"
   href="/register">
Create Account
</a>

</nav>

</div>

</header>


{% with messages=get_flashed_messages(with_categories=true) %}

{% for category,message in messages %}

<div class="alert {{ category }}">
{{ message }}
</div>

{% endfor %}

{% endwith %}


<main class="container">

{{ content|safe }}

</main>


<footer>

<strong>KOJA AFRICA</strong>

<br>

Knowledge • Questions • Answers

</footer>

</body>
</html>
"""


PRIVATE_LAYOUT = r"""
<!doctype html>
<html>

<head>

<meta charset="utf-8">

<meta name="viewport"
      content="width=device-width,initial-scale=1">

<meta name="robots"
      content="noindex,nofollow,noarchive">

<title>{{ title }} | KOJA AFRICA</title>

""" + CSS + r"""

</head>

<body>

<header class="topbar">

<div class="topbar-inner">

<button class="menu"
        onclick="document.getElementById('nav').classList.toggle('open')">
☰
</button>


<a class="brand"
   href="/">

<div>

<div class="logo">

<span class="k">k</span>
<span class="o">o</span>
<span class="j">j</span>
<span class="a">a</span>

</div>

<div class="africa">
AFRICA
</div>

</div>

</a>


<div class="search">

<span class="search-icon">
⌕
</span>

<input
placeholder="Search research..."
onkeydown="
if(event.key==='Enter'){
location='/research?q='+
encodeURIComponent(this.value)
}
">

</div>


<div class="profile">

{{ (session.get('role','U')[0]
if session.get('role')
else 'U')|upper }}

<span class="online"></span>

</div>


<nav class="nav"
     id="nav">

{% if session.get("role") == "admin" %}

<a href="/admin">
Dashboard
</a>

<a href="/admin/questions">
Questions
</a>

<a href="/admin/answers">
Answers
</a>

<a href="/admin/documents">
Documents
</a>

<a href="/admin/logs">
Logs
</a>

{% else %}

<a href="/student">
Dashboard
</a>

<a href="/ask">
Ask Question
</a>

<a href="/student/questions">
My Questions
</a>

<a href="/research">
Research
</a>

<a href="/student/documents">
Documents
</a>

{% endif %}

<a href="/logout">
Logout
</a>

</nav>

</div>

</header>


{% with messages=get_flashed_messages(with_categories=true) %}

{% for category,message in messages %}

<div class="alert {{ category }}">
{{ message }}
</div>

{% endfor %}

{% endwith %}


<main class="container">

{{ content|safe }}

</main>


{% if session.get("role") == "student" %}

<nav class="mobile-bottom">

<a href="/student">
<strong>⌂</strong>
Dashboard
</a>

<a href="/ask">
<strong>＋</strong>
Ask
</a>

<a href="/student/documents">
<strong>□</strong>
Documents
</a>

<a href="/logout">
<strong>→</strong>
Logout
</a>

</nav>

{% endif %}


<footer>

<strong>KOJA AFRICA</strong>

<br>

Knowledge • Questions • Answers

</footer>

</body>
</html>
"""


def public_page(title, content):
    return render_template_string(
        PUBLIC_LAYOUT,
        title=title,
        content=content
    )


def private_page(title, content):
    return render_template_string(
        PRIVATE_LAYOUT,
        title=title,
        content=content
    )


# ============================================================
# HOME
# ============================================================

@app.route("/")
def home():

    content = r"""

<section class="card"
style="
text-align:center;
max-width:1050px;
margin:65px auto;
padding:70px 25px
">

<div class="logo">

<span class="k">K</span>
<span class="o">O</span>
<span class="j">J</span>
<span class="a">A</span>

</div>

<div class="africa">
AFRICA
</div>

<h2>
Knowledge • Questions • Answers
</h2>

<p style="
max-width:760px;
margin:20px auto;
color:#b7bfda;
font-size:19px;
line-height:1.7
">

Academic questions, research,
learning resources and educational
support in one platform.

</p>

<div class="actions"
style="justify-content:center">

<a class="btn"
href="/login">
Log In
</a>

<a class="btn2"
href="/register">
Create Account
</a>

</div>

</section>

"""

    return public_page(
        "Home",
        content
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

        name = request.form.get(
            "name",
            ""
        ).strip()

        email = request.form.get(
            "email",
            ""
        ).strip().lower()

        password = request.form.get(
            "password",
            ""
        )

        if not name or not email or not password:

            flash(
                "Complete all fields.",
                "error"
            )

            return redirect(
                "/register"
            )

        if len(password) < 6:

            flash(
                "Password must contain at least 6 characters.",
                "error"
            )

            return redirect(
                "/register"
            )

        try:

            existing = get_profile_by_email(
                email
            )

            if existing:

                flash(
                    "An account with that email already exists.",
                    "error"
                )

                return redirect(
                    "/register"
                )

            response = supabase_signup(
                email,
                password
            )

            if not response.ok:

                try:
                    error = response.json()
                    message = (
                        error.get("msg")
                        or error.get("message")
                        or "Registration failed."
                    )
                except Exception:
                    message = "Registration failed."

                flash(
                    message,
                    "error"
                )

                return redirect(
                    "/register"
                )

            auth_data = response.json()

            user_data = auth_data.get(
                "user"
            )

            if not user_data:

                flash(
                    "Registration was not completed.",
                    "error"
                )

                return redirect(
                    "/register"
                )

            user_id = user_data.get(
                "id"
            )

            # Profile creation.
            #
            # If email confirmation is enabled,
            # this still creates the profile.
            create_profile(
                user_id,
                name,
                email,
                "student"
            )

            log_event(
                "Student Account Created",
                "Authentication",
                "INFO",
                email
            )

            flash(
                "Account created successfully. Please log in.",
                "success"
            )

            return redirect(
                "/login"
            )

        except Exception as exc:

            print(
                "REGISTER ERROR:",
                exc
            )

            flash(
                "Unable to create account. Check Supabase configuration.",
                "error"
            )

            return redirect(
                "/register"
            )

    content = r"""

<div class="auth">

<div class="card">

<h1>
Create Account
</h1>

<p class="muted">
Create your KOJA AFRICA student account.
</p>

<form method="post">

<label>
Name
</label>

<input
class="form-control"
name="name"
required
>

<label>
Email
</label>

<input
class="form-control"
type="email"
name="email"
required
>

<label>
Password
</label>

<input
class="form-control"
type="password"
name="password"
minlength="6"
required
>

<button
class="btn"
type="submit"
>
Create Account
</button>

</form>

</div>

</div>

"""

    return public_page(
        "Create Account",
        content
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

        if not email or not password:

            flash(
                "Enter your email and password.",
                "error"
            )

            return redirect(
                "/login"
            )

        try:

            response = supabase_login(
                email,
                password
            )

            if not response.ok:

                log_event(
                    "Failed Login",
                    "Authentication",
                    "WARNING",
                    email
                )

                flash(
                    "Invalid email or password.",
                    "error"
                )

                return redirect(
                    "/login"
                )

            data = response.json()

            user_data = data.get(
                "user"
            )

            access_token = data.get(
                "access_token"
            )

            if not user_data or not access_token:

                flash(
                    "Login failed.",
                    "error"
                )

                return redirect(
                    "/login"
                )

            user_id = user_data.get(
                "id"
            )

            profile = get_profile(
                user_id
            )

            if not profile:

                profile = create_profile(
                    user_id,
                    user_data.get(
                        "user_metadata",
                        {}
                    ).get(
                        "name",
                        email.split("@")[0]
                    ),
                    email,
                    "student"
                )

            session.clear()

            session["user_id"] = user_id

            session["role"] = profile.get(
                "role",
                "student"
            )

            session["access_token"] = access_token

            log_event(
                "Login",
                "Authentication",
                "INFO",
                email
            )

            if profile.get("role") == "admin":

                return redirect(
                    "/admin"
                )

            return redirect(
                "/student"
            )

        except Exception as exc:

            print(
                "LOGIN ERROR:",
                exc
            )

            flash(
                "Unable to connect to Supabase.",
                "error"
            )

            return redirect(
                "/login"
            )

    content = r"""

<div class="auth">

<div class="card">

<h1>
Log In
</h1>

<p class="muted">
Access your KOJA AFRICA portal.
</p>

<form method="post">

<label>
Email
</label>

<input
class="form-control"
type="email"
name="email"
required
>

<label>
Password
</label>

<input
class="form-control"
type="password"
name="password"
required
>

<button
class="btn"
type="submit"
>
Log In
</button>

</form>

</div>

</div>

"""

    return public_page(
        "Log In",
        content
    )


# ============================================================
# LOGOUT
# ============================================================

@app.route("/logout")
def logout():

    token = session.get(
        "access_token"
    )

    if current_user():

        log_event(
            "Logout",
            "Authentication",
            "INFO"
        )

    supabase_logout(
        token
    )

    session.clear()

    return redirect("/")


# ============================================================
# STUDENT DASHBOARD
# ============================================================

@app.route("/student")
@login_required
def student_dashboard():

    user = current_user()

    if user["role"] == "admin":

        return redirect(
            "/admin"
        )

    questions = supabase_get(
        "questions",
        {
            "student_id":
                f"eq.{user['id']}",
            "select": "*",
            "order":
                "created_at.desc"
        }
    )

    received = supabase_get(
        "documents",
        {
            "recipient_id":
                f"eq.{user['id']}",
            "direction":
                "eq.admin_to_student",
            "select": "*",
            "order":
                "created_at.desc"
        }
    )

    sent = supabase_get(
        "documents",
        {
            "sender_id":
                f"eq.{user['id']}",
            "direction":
                "eq.student_to_admin",
            "select": "*",
            "order":
                "created_at.desc"
        }
    )

    answered = sum(
        1 for q in questions
        if q.get("answer")
    )

    first = esc(
        user.get(
            "name",
            "Student"
        ).split()[0]
    )

    content = f"""

<section class="card hero">

<div class="greeting">
☼ &nbsp; Good morning, {first}
</div>

<h1>
Welcome back<span>.</span>
</h1>

<p>
Here is a quick overview of your dashboard.
Manage your <strong>KOJA AFRICA</strong>
portal activities and monitor your progress below.
</p>

<div class="actions">

<a class="btn"
href="/ask">
▤ &nbsp; Ask Question
</a>

<a class="btn2"
href="/student/questions">
□ &nbsp; My Questions
</a>

<a class="btn green"
href="/research">
⌕ &nbsp; Research
</a>

</div>


<div class="stats">

<div class="stat">

<div class="stat-icon">
?
</div>

<h2>
{len(questions)}
</h2>

<p>
My Questions<br>
Total
</p>

</div>


<div class="stat">

<div class="stat-icon">
✓
</div>

<h2>
{answered}
</h2>

<p>
Answered<br>
Questions
</p>

</div>


<div class="stat">

<div class="stat-icon">
▤
</div>

<h2>
{len(received)}
</h2>

<p>
Documents<br>
Received
</p>

</div>


<div class="stat">

<div class="stat-icon">
↑
</div>

<h2>
{len(sent)}
</h2>

<p>
Documents<br>
Sent
</p>

</div>

</div>

</section>


<div class="section-title">

<h2>
Quick Access
</h2>

</div>


<section class="quick-grid">

<a class="quick"
href="/ask">

<div class="quick-icon">
▤
</div>

<h3>
Ask Question
</h3>

<p>
Get academic answers
</p>

</a>


<a class="quick"
href="/student/questions">

<div class="quick-icon">
□
</div>

<h3>
My Questions
</h3>

<p>
Track your questions
</p>

</a>


<a class="quick"
href="/research">

<div class="quick-icon">
▥
</div>

<h3>
Research
</h3>

<p>
Explore answered questions
</p>

</a>


<a class="quick"
href="/student/documents">

<div class="quick-icon">
▱
</div>

<h3>
My Documents
</h3>

<p>
Upload and download files
</p>

</a>


<a class="quick"
href="/student/documents">

<div class="quick-icon">
♧
</div>

<h3>
Notifications
</h3>

<p>
Stay updated with KOJA
</p>

</a>


<a class="quick"
href="/student">

<div class="quick-icon">
♙
</div>

<h3>
My Profile
</h3>

<p>
{esc(user.get("name"))}
</p>

</a>

</section>

"""

    return private_page(
        "Student Dashboard",
        content
    )


# ============================================================
# ASK QUESTION
# ============================================================

@app.route(
    "/ask",
    methods=["GET", "POST"]
)
@login_required
def ask_question():

    user = current_user()

    if user["role"] == "admin":

        return redirect(
            "/admin"
        )

    if request.method == "POST":

        text = request.form.get(
            "question",
            ""
        ).strip()

        if not text:

            flash(
                "Enter your question.",
                "error"
            )

            return redirect(
                "/ask"
            )

        try:

            rows = supabase_insert(
                "questions",
                {
                    "student_id":
                        user["id"],
                    "student_name":
                        user["name"],
                    "question":
                        text,
                    "answer":
                        "",
                    "answer_by":
                        ""
                }
            )

            question = rows[0]

            question_id = question["id"]

            file = request.files.get(
                "document"
            )

            if file and file.filename:

                saved = storage_upload(
                    file,
                    f"questions/{question_id}"
                )

                supabase_insert(
                    "question_files",
                    {
                        "question_id":
                            question_id,
                        "original_name":
                            saved["original_name"],
                        "storage_path":
                            saved["storage_path"],
                        "size":
                            saved["size"],
                        "file_type":
                            "question"
                    }
                )

            log_event(
                "Question Submitted",
                "Questions",
                "INFO",
                str(question_id)
            )

            flash(
                "Your question has been submitted.",
                "success"
            )

            return redirect(
                "/student/questions"
            )

        except Exception as exc:

            print(
                "QUESTION ERROR:",
                exc
            )

            flash(
                "Unable to submit your question.",
                "error"
            )

            return redirect(
                "/ask"
            )

    content = r"""

<div class="card">

<h1>
Ask KOJA
</h1>

<p class="muted">
Submit an academic question to
KOJA Administration.
</p>

<form method="post"
      enctype="multipart/form-data">

<label>
Question
</label>

<textarea
class="form-control"
name="question"
required>
</textarea>

<label>
Optional supporting document
</label>

<input
class="form-control"
type="file"
name="document"
>

<p class="muted">
PDF, Word, Excel, PowerPoint,
text, images and CSV.
Maximum 15 MB.
</p>

<button
class="btn"
type="submit">
Submit Question
</button>

</form>

</div>

"""

    return private_page(
        "Ask Question",
        content
    )


# ============================================================
# STUDENT QUESTIONS
# ============================================================

@app.route("/student/questions")
@login_required
def student_questions():

    user = current_user()

    questions = supabase_get(
        "questions",
        {
            "student_id":
                f"eq.{user['id']}",
            "select": "*",
            "order":
                "created_at.desc"
        }
    )

    blocks = []

    for q in questions:

        status = (
            "Answered"
            if q.get("answer")
            else "Pending"
        )

        status_class = (
            "answered"
            if q.get("answer")
            else "pending"
        )

        files = supabase_get(
            "question_files",
            {
                "question_id":
                    f"eq.{q['id']}",
                "select": "*",
                "order":
                    "created_at.asc"
            }
        )

        attachments = ""

        for f in files:

            attachments += f"""

<div class="document-box">

<strong>
Your supporting document
</strong>

<br><br>

{esc(f.get("original_name"))}

<br><br>

<a class="btn2"
href="{url_for(
    'question_file_download',
    file_id=f['id']
)}">

Download

</a>

</div>

"""

        answer = ""

        if q.get("answer"):

            answer = f"""

<h3>
Answer
</h3>

<div class="answer">
{esc(q.get("answer"))}
</div>

<p class="muted">
Answered by:
{esc(q.get("answer_by", "KOJA Administration"))}
</p>

"""

        answer_files = supabase_get(
            "question_files",
            {
                "question_id":
                    f"eq.{q['id']}",
                "file_type":
                    "eq.answer",
                "select": "*"
            }
        )

        for f in answer_files:

            answer += f"""

<div class="document-box">

<strong>
Document from KOJA Administration
</strong>

<br><br>

{esc(f.get("original_name"))}

<br><br>

<a class="btn green"
href="{url_for(
    'question_file_download',
    file_id=f['id']
)}">

Download Document

</a>

</div>

"""

        blocks.append(f"""

<div class="card">

<h2>
{esc(q.get("question"))}
</h2>

<p>

<span class="badge {status_class}">
{status}
</span>

</p>

{attachments}

{answer}

</div>

""")

    content = """

<div class="card">

<h1>
My Questions
</h1>

<p class="muted">
Only your questions and their answers
are shown here.
</p>

</div>

"""

    content += (
        "".join(blocks)
        if blocks
        else
        '<div class="card empty">'
        'You have not submitted a question yet.'
        '</div>'
    )

    return private_page(
        "My Questions",
        content
    )


# ============================================================
# QUESTION FILE DOWNLOAD
# ============================================================

@app.route(
    "/question-file/<file_id>"
)
@login_required
def question_file_download(file_id):

    user = current_user()

    rows = supabase_get(
        "question_files",
        {
            "id":
                f"eq.{file_id}",
            "select": "*",
            "limit": "1"
        }
    )

    if not rows:
        abort(404)

    file_record = rows[0]

    question_rows = supabase_get(
        "questions",
        {
            "id":
                f"eq.{file_record['question_id']}",
            "select": "student_id",
            "limit": "1"
        }
    )

    if not question_rows:
        abort(404)

    question = question_rows[0]

    if (
        user["role"] != "admin"
        and question["student_id"] != user["id"]
    ):
        abort(403)

    response = storage_download(
        file_record["storage_path"]
    )

    if not response:
        abort(404)

    log_event(
        "Question File Downloaded",
        "Documents",
        "INFO",
        file_record["original_name"]
    )

    from io import BytesIO

    return send_file(
        BytesIO(response.content),
        as_attachment=True,
        download_name=file_record[
            "original_name"
        ],
        mimetype=response.headers.get(
            "Content-Type",
            "application/octet-stream"
        )
    )


# ============================================================
# RESEARCH
# ============================================================

@app.route("/research")
@login_required
def research():

    query = request.args.get(
        "q",
        ""
    ).strip()

    questions = supabase_get(
        "questions",
        {
            "answer":
                "not.is.null",
            "select": "*",
            "order":
                "created_at.desc"
        }
    )

    questions = [
        q for q in questions
        if q.get("answer")
    ]

    if query:

        query_lower = query.lower()

        questions = [
            q for q in questions
            if query_lower in
            q.get(
                "question",
                ""
            ).lower()
            or
            query_lower in
            q.get(
                "answer",
                ""
            ).lower()
        ]

    blocks = []

    for q in questions:

        blocks.append(f"""

<div class="card">

<h2>
{esc(q.get("question"))}
</h2>

<div class="answer">
{esc(q.get("answer"))}
</div>

</div>

""")

    content = f"""

<div class="card">

<h1>
Research
</h1>

<p class="muted">
Search answered academic questions
and learning content.
</p>

<form method="get">

<input
class="form-control"
name="q"
value="{esc(query)}"
placeholder="Search questions and answers"
>

<button
class="btn"
type="submit">
Search
</button>

</form>

</div>

"""

    content += (
        "".join(blocks)
        if blocks
        else
        '<div class="card empty">'
        'No answered research results found.'
        '</div>'
    )

    return private_page(
        "Research",
        content
    )


# ============================================================
# STUDENT DOCUMENTS
# ============================================================

@app.route(
    "/student/documents",
    methods=["GET", "POST"]
)
@login_required
def student_documents():

    user = current_user()

    if user["role"] == "admin":

        return redirect(
            "/admin/documents"
        )

    if request.method == "POST":

        title = request.form.get(
            "title",
            ""
        ).strip()

        description = request.form.get(
            "description",
            ""
        ).strip()

        file = request.files.get(
            "document"
        )

        if not title:

            flash(
                "Enter a document title.",
                "error"
            )

            return redirect(
                "/student/documents"
            )

        if not file or not file.filename:

            flash(
                "Select a document.",
                "error"
            )

            return redirect(
                "/student/documents"
            )

        try:

            saved = storage_upload(
                file,
                f"student-documents/{user['id']}"
            )

            rows = supabase_insert(
                "documents",
                {
                    "direction":
                        "student_to_admin",
                    "sender_id":
                        user["id"],
                    "sender_name":
                        user["name"],
                    "recipient_id":
                        None,
                    "recipient_name":
                        "KOJA Administration",
                    "title":
                        title,
                    "description":
                        description,
                    "original_name":
                        saved["original_name"],
                    "storage_path":
                        saved["storage_path"],
                    "size":
                        saved["size"]
                }
            )

            log_event(
                "Student Document Submitted",
                "Documents",
                "INFO",
                saved["original_name"]
            )

            flash(
                "Your document has been sent to KOJA Administration.",
                "success"
            )

            return redirect(
                "/student/documents"
            )

        except Exception as exc:

            print(
                "DOCUMENT ERROR:",
                exc
            )

            flash(
                "Unable to upload the document.",
                "error"
            )

            return redirect(
                "/student/documents"
            )

    received = supabase_get(
        "documents",
        {
            "recipient_id":
                f"eq.{user['id']}",
            "direction":
                "eq.admin_to_student",
            "select": "*",
            "order":
                "created_at.desc"
        }
    )

    sent = supabase_get(
        "documents",
        {
            "sender_id":
                f"eq.{user['id']}",
            "direction":
                "eq.student_to_admin",
            "select": "*",
            "order":
                "created_at.desc"
        }
    )

    received_rows = ""

    for d in received:

        received_rows += f"""

<tr>

<td>
{esc(d.get("created_at",""))}
</td>

<td>
<strong>
{esc(d.get("title",""))}
</strong>
</td>

<td>
{esc(d.get("original_name",""))}
<br>
<span class="muted">
{size_text(d.get("size",0))}
</span>
</td>

<td>
{esc(d.get("description",""))}
</td>

<td>

<a class="btn green"
href="{url_for(
    'document_download',
    document_id=d['id']
)}">

Download

</a>

</td>

</tr>

"""

    if not received_rows:

        received_rows = """
<tr>
<td colspan="5">
No documents received yet.
</td>
</tr>
"""

    sent_rows = ""

    for d in sent:

        sent_rows += f"""

<tr>

<td>
{esc(d.get("created_at",""))}
</td>

<td>
{esc(d.get("title",""))}
</td>

<td>
{esc(d.get("original_name",""))}
<br>
<span class="muted">
{size_text(d.get("size",0))}
</span>
</td>

<td>
Sent to KOJA Administration
</td>

<td>
<a class="btn2"
href="{url_for(
    'document_download',
    document_id=d['id']
)}">

Download

</a>
</td>

</tr>

"""

    if not sent_rows:

        sent_rows = """
<tr>
<td colspan="5">
You have not sent a document yet.
</td>
</tr>
"""

    content = f"""

<div class="card">

<h1>
My Documents
</h1>

<p class="muted">
Send documents to KOJA Administration
and download documents sent specifically
to you.
</p>

</div>


<div class="card">

<h2>
Send Document To KOJA Administration
</h2>

<form method="post"
enctype="multipart/form-data">

<label>
Document Title
</label>

<input
class="form-control"
name="title"
required
>

<label>
Description
</label>

<textarea
class="form-control"
name="description"
style="min-height:120px">
</textarea>

<label>
Document
</label>

<input
class="form-control"
type="file"
name="document"
required
>

<button
class="btn"
type="submit">
Send Document
</button>

</form>

</div>


<div class="card">

<h2>
Documents Received From KOJA
</h2>

<div class="table-wrap">

<table>

<tr>
<th>Date</th>
<th>Title</th>
<th>File</th>
<th>Description</th>
<th>Download</th>
</tr>

{received_rows}

</table>

</div>

</div>


<div class="card">

<h2>
Documents I Sent
</h2>

<div class="table-wrap">

<table>

<tr>
<th>Date</th>
<th>Title</th>
<th>File</th>
<th>Status</th>
<th>Download</th>
</tr>

{sent_rows}

</table>

</div>

</div>

"""

    return private_page(
        "My Documents",
        content
    )


# ============================================================
# DOCUMENT DOWNLOAD
# ============================================================

@app.route(
    "/document/<document_id>/download"
)
@login_required
def document_download(document_id):

    user = current_user()

    rows = supabase_get(
        "documents",
        {
            "id":
                f"eq.{document_id}",
            "select": "*",
            "limit": "1"
        }
    )

    if not rows:
        abort(404)

    document = rows[0]

    allowed = (
        user["role"] == "admin"
        or document.get("sender_id") == user["id"]
        or document.get("recipient_id") == user["id"]
    )

    if not allowed:
        abort(403)

    response = storage_download(
        document["storage_path"]
    )

    if not response:
        abort(404)

    log_event(
        "Document Downloaded",
        "Documents",
        "INFO",
        document.get(
            "original_name",
            ""
        )
    )

    from io import BytesIO

    return send_file(
        BytesIO(response.content),
        as_attachment=True,
        download_name=document[
            "original_name"
        ],
        mimetype=response.headers.get(
            "Content-Type",
            "application/octet-stream"
        )
    )


# ============================================================
# ADMIN DASHBOARD
# ============================================================

@app.route("/admin")
@admin_required
def admin_dashboard():

    users = supabase_get(
        "profiles",
        {
            "role":
                "eq.student",
            "select":
                "id"
        }
    )

    questions = supabase_get(
        "questions",
        {
            "select":
                "id,answer"
        }
    )

    documents = supabase_get(
        "documents",
        {
            "direction":
                "eq.student_to_admin",
            "select":
                "id"
        }
    )

    answered = [
        q for q in questions
        if q.get("answer")
    ]

    content = f"""

<section class="card hero">

<div class="greeting">
◉ &nbsp; Administration
</div>

<h1>
KOJA AFRICA<span>.</span>
</h1>

<p>
Manage student questions,
academic answers, documents
and private system activity.
</p>


<div class="actions">

<a class="btn"
href="/admin/questions">
▤ &nbsp; Questions
</a>

<a class="btn2"
href="/admin/documents">
□ &nbsp; Documents
</a>

<a class="btn green"
href="/admin/answers">
✓ &nbsp; Answers
</a>

</div>


<div class="stats">

<div class="stat">

<div class="stat-icon">
♙
</div>

<h2>
{len(users)}
</h2>

<p>
Students
</p>

</div>


<div class="stat">

<div class="stat-icon">
?
</div>

<h2>
{len(questions)}
</h2>

<p>
Questions
</p>

</div>


<div class="stat">

<div class="stat-icon">
✓
</div>

<h2>
{len(answered)}
</h2>

<p>
Answered
</p>

</div>


<div class="stat">

<div class="stat-icon">
□
</div>

<h2>
{len(documents)}
</h2>

<p>
Student Documents
</p>

</div>

</div>

</section>


<div class="section-title">

<h2>
Admin Quick Access
</h2>

</div>


<section class="quick-grid">

<a class="quick"
href="/admin/questions">

<div class="quick-icon">
?
</div>

<h3>
Questions
</h3>

<p>
Review and answer student questions.
</p>

</a>


<a class="quick"
href="/admin/answers">

<div class="quick-icon">
✓
</div>

<h3>
Answers
</h3>

<p>
Review completed academic answers.
</p>

</a>


<a class="quick"
href="/admin/documents">

<div class="quick-icon">
□
</div>

<h3>
Documents
</h3>

<p>
Receive and send student files.
</p>

</a>


<a class="quick"
href="/admin/logs">

<div class="quick-icon">
◌
</div>

<h3>
Logs
</h3>

<p>
Private administrator activity records.
</p>

</a>

</section>

"""

    return private_page(
        "Admin Dashboard",
        content
    )


# ============================================================
# ADMIN QUESTIONS
# ============================================================

@app.route("/admin/questions")
@admin_required
def admin_questions():

    questions = supabase_get(
        "questions",
        {
            "select":
                "*",
            "order":
                "created_at.desc"
        }
    )

    blocks = []

    for q in questions:

        status = (
            "Answered"
            if q.get("answer")
            else "Pending"
        )

        cls = (
            "answered"
            if q.get("answer")
            else "pending"
        )

        files = supabase_get(
            "question_files",
            {
                "question_id":
                    f"eq.{q['id']}",
                "file_type":
                    "eq.question",
                "select":
                    "*"
            }
        )

        file_html = ""

        for f in files:

            file_html += f"""

<div class="document-box">

<strong>
Student Document
</strong>

<br><br>

{esc(f.get("original_name"))}

<br><br>

<a class="btn2"
href="{url_for(
    'question_file_download',
    file_id=f['id']
)}">

Download Student Document

</a>

</div>

"""

        blocks.append(f"""

<div class="card">

<h2>
{esc(q.get("question"))}
</h2>

<p>
Student:
<strong>
{esc(q.get("student_name"))}
</strong>
</p>

<p>

<span class="badge {cls}">
{status}
</span>

</p>

{file_html}

<a class="btn"
href="{url_for(
    'admin_answer',
    question_id=q['id']
)}">

Answer Question

</a>

</div>

""")

    content = """

<div class="card">

<h1>
Questions
</h1>

<p class="muted">
Only administrators can see submitted
student questions.
</p>

</div>

"""

    content += (
        "".join(blocks)
        if blocks
        else
        '<div class="card empty">'
        'No questions have been submitted.'
        '</div>'
    )

    return private_page(
        "Questions",
        content
    )


# ============================================================
# ADMIN ANSWER
# ============================================================

@app.route(
    "/admin/answer/<question_id>",
    methods=["GET", "POST"]
)
@admin_required
def admin_answer(question_id):

    rows = supabase_get(
        "questions",
        {
            "id":
                f"eq.{question_id}",
            "select":
                "*",
            "limit":
                "1"
        }
    )

    if not rows:
        abort(404)

    question = rows[0]

    if request.method == "POST":

        answer = request.form.get(
            "answer",
            ""
        ).strip()

        if not answer:

            flash(
                "Enter an answer.",
                "error"
            )

            return redirect(
                url_for(
                    "admin_answer",
                    question_id=question_id
                )
            )

        try:

            admin = current_user()

            supabase_update(
                "questions",
                {
                    "answer":
                        answer,
                    "answer_by":
                        admin["name"],
                    "answered_at":
                        now_iso()
                },
                {
                    "id":
                        f"eq.{question_id}"
                }
            )

            file = request.files.get(
                "document"
            )

            if file and file.filename:

                saved = storage_upload(
                    file,
                    f"answers/{question_id}"
                )

                supabase_insert(
                    "question_files",
                    {
                        "question_id":
                            question_id,
                        "original_name":
                            saved["original_name"],
                        "storage_path":
                            saved["storage_path"],
                        "size":
                            saved["size"],
                        "file_type":
                            "answer"
                    }
                )

            log_event(
                "Question Answered",
                "Answers",
                "INFO",
                question_id
            )

            flash(
                "Answer saved successfully.",
                "success"
            )

            return redirect(
                "/admin/questions"
            )

        except Exception as exc:

            print(
                "ANSWER ERROR:",
                exc
            )

            flash(
                "Unable to save the answer.",
                "error"
            )

            return redirect(
                url_for(
                    "admin_answer",
                    question_id=question_id
                )
            )

    content = f"""

<div class="card">

<h1>
Answer Question
</h1>

<p>
Student:
<strong>
{esc(question.get("student_name"))}
</strong>
</p>

<div class="question">
{esc(question.get("question"))}
</div>

<form method="post"
enctype="multipart/form-data">

<label>
Answer
</label>

<textarea
class="form-control"
name="answer"
required>{esc(
question.get("answer","")
)}</textarea>

<label>
Attach answer document
</label>

<input
class="form-control"
type="file"
name="document"
>

<button
class="btn"
type="submit">

Save Answer

</button>

</form>

</div>

"""

    return private_page(
        "Answer Question",
        content
    )


# ============================================================
# ADMIN ANSWERS
# ============================================================

@app.route("/admin/answers")
@admin_required
def admin_answers():

    answered = supabase_get(
        "questions",
        {
            "answer":
                "not.is.null",
            "select":
                "*",
            "order":
                "answered_at.desc"
        }
    )

    answered = [
        q for q in answered
        if q.get("answer")
    ]

    blocks = []

    for q in answered:

        blocks.append(f"""

<div class="card">

<h2>
{esc(q.get("question"))}
</h2>

<div class="answer">
{esc(q.get("answer"))}
</div>

<p>
Student:
{esc(q.get("student_name"))}
</p>

<p>
Answered by:
{esc(q.get("answer_by","Admin"))}
</p>

</div>

""")

    content = """

<div class="card">

<h1>
Answers
</h1>

<p class="muted">
This section is visible only to administrators.
</p>

</div>

"""

    content += (
        "".join(blocks)
        if blocks
        else
        '<div class="card empty">'
        'No answers yet.'
        '</div>'
    )

    return private_page(
        "Answers",
        content
    )


# ============================================================
# ADMIN DOCUMENTS
# ============================================================

@app.route(
    "/admin/documents",
    methods=["GET", "POST"]
)
@admin_required
def admin_documents():

    admin = current_user()

    student_list = supabase_get(
        "profiles",
        {
            "role":
                "eq.student",
            "select":
                "id,name,email",
            "order":
                "name.asc"
        }
    )

    if request.method == "POST":

        student_id = request.form.get(
            "student_id",
            ""
        ).strip()

        title = request.form.get(
            "title",
            ""
        ).strip()

        description = request.form.get(
            "description",
            ""
        ).strip()

        file = request.files.get(
            "document"
        )

        student = next(
            (
                s for s in student_list
                if s["id"] == student_id
            ),
            None
        )

        if not student:

            flash(
                "Please select a valid student.",
                "error"
            )

            return redirect(
                "/admin/documents"
            )

        if not title:

            flash(
                "Enter a document title.",
                "error"
            )

            return redirect(
                "/admin/documents"
            )

        if not file or not file.filename:

            flash(
                "Select a document.",
                "error"
            )

            return redirect(
                "/admin/documents"
            )

        try:

            saved = storage_upload(
                file,
                f"admin-documents/{student_id}"
            )

            supabase_insert(
                "documents",
                {
                    "direction":
                        "admin_to_student",
                    "sender_id":
                        admin["id"],
                    "sender_name":
                        admin["name"],
                    "recipient_id":
                        student["id"],
                    "recipient_name":
                        student["name"],
                    "title":
                        title,
                    "description":
                        description,
                    "original_name":
                        saved["original_name"],
                    "storage_path":
                        saved["storage_path"],
                    "size":
                        saved["size"]
                }
            )

            log_event(
                "Document Sent To Student",
                "Documents",
                "INFO",
                f'{saved["original_name"]} -> {student["email"]}'
            )

            flash(
                f'Document sent to {student["name"]}.',
                "success"
            )

            return redirect(
                "/admin/documents"
            )

        except Exception as exc:

            print(
                "ADMIN DOCUMENT ERROR:",
                exc
            )

            flash(
                "Unable to send document.",
                "error"
            )

            return redirect(
                "/admin/documents"
            )

    received = supabase_get(
        "documents",
        {
            "direction":
                "eq.student_to_admin",
            "select":
                "*",
            "order":
                "created_at.desc"
        }
    )

    sent = supabase_get(
        "documents",
        {
            "direction":
                "eq.admin_to_student",
            "select":
                "*",
            "order":
                "created_at.desc"
        }
    )

    options = ""

    for s in student_list:

        options += f"""

<option value="{esc(s['id'])}">

{esc(s['name'])}
-
{esc(s['email'])}

</option>

"""

    received_rows = ""

    for d in received:

        received_rows += f"""

<tr>

<td>
{esc(d.get("created_at",""))}
</td>

<td>
{esc(d.get("sender_name","Student"))}
</td>

<td>
{esc(d.get("title",""))}
</td>

<td>

{esc(d.get("original_name",""))}

<br>

<span class="muted">

{size_text(d.get("size",0))}

</span>

</td>

<td>

<a class="btn2"
href="{url_for(
    'document_download',
    document_id=d['id']
)}">

Download

</a>

</td>

</tr>

"""

    if not received_rows:

        received_rows = """
<tr>
<td colspan="5">
No documents received.
</td>
</tr>
"""

    sent_rows = ""

    for d in sent:

        sent_rows += f"""

<tr>

<td>
{esc(d.get("created_at",""))}
</td>

<td>
{esc(d.get("recipient_name",""))}
</td>

<td>
{esc(d.get("title",""))}
</td>

<td>
{esc(d.get("original_name",""))}
</td>

<td>

<a class="btn2"
href="{url_for(
    'document_download',
    document_id=d['id']
)}">

Download

</a>

</td>

</tr>

"""

    if not sent_rows:

        sent_rows = """
<tr>
<td colspan="5">
No documents sent.
</td>
</tr>
"""

    content = f"""

<div class="card">

<h1>
Documents
</h1>

<p class="muted">
Private administrator document management.
</p>

</div>


<div class="card">

<h2>
Send Document To Student
</h2>

<form method="post"
enctype="multipart/form-data">

<label>
Student
</label>

<select
class="form-control"
name="student_id"
required>

<option value="">
Select student
</option>

{options}

</select>


<label>
Document Title
</label>

<input
class="form-control"
name="title"
required
>


<label>
Description
</label>

<textarea
class="form-control"
name="description"
style="min-height:120px">
</textarea>


<label>
Document
</label>

<input
class="form-control"
type="file"
name="document"
required
>


<button
class="btn"
type="submit">

Send Document

</button>

</form>

</div>


<div class="card">

<h2>
Documents Received From Students
</h2>

<div class="table-wrap">

<table>

<tr>
<th>Date</th>
<th>Student</th>
<th>Title</th>
<th>File</th>
<th>Download</th>
</tr>

{received_rows}

</table>

</div>

</div>


<div class="card">

<h2>
Documents Sent To Students
</h2>

<div class="table-wrap">

<table>

<tr>
<th>Date</th>
<th>Student</th>
<th>Title</th>
<th>File</th>
<th>Download</th>
</tr>

{sent_rows}

</table>

</div>

</div>

"""

    return private_page(
        "Documents",
        content
    )


# ============================================================
# ADMIN LOGS
# ============================================================

@app.route("/admin/logs")
@admin_required
def admin_logs():

    logs = supabase_get(
        "logs",
        {
            "select":
                "*",
            "order":
                "created_at.desc",
            "limit":
                "500"
        }
    )

    rows = ""

    for x in logs:

        rows += f"""

<tr>

<td>
{esc(x.get("created_at",""))}
</td>

<td>
{esc(x.get("event",""))}
</td>

<td>
{esc(x.get("category",""))}
</td>

<td>
{esc(x.get("level",""))}
</td>

<td>
{esc(x.get("details",""))}
</td>

</tr>

"""

    if not rows:

        rows = """
<tr>
<td colspan="5">
No logs.
</td>
</tr>
"""

    content = f"""

<div class="card">

<h1>
System Logs
</h1>

<p class="muted">
Private administrator information.
Students cannot access this page.
</p>

<div class="table-wrap">

<table>

<tr>

<th>
Time
</th>

<th>
Event
</th>

<th>
Category
</th>

<th>
Level
</th>

<th>
Details
</th>

</tr>

{rows}

</table>

</div>

</div>

"""

    return private_page(
        "Logs",
        content
    )


# ============================================================
# SECURITY HEADERS
# ============================================================

@app.after_request
def security_headers(response):

    response.headers[
        "X-Content-Type-Options"
    ] = "nosniff"

    response.headers[
        "X-Frame-Options"
    ] = "SAMEORIGIN"

    response.headers[
        "Referrer-Policy"
    ] = "strict-origin-when-cross-origin"

    if request.path.startswith(
        (
            "/admin",
            "/student",
            "/ask",
            "/research"
        )
    ):

        response.headers[
            "Cache-Control"
        ] = (
            "no-store, "
            "no-cache, "
            "must-revalidate, "
            "private"
        )

        response.headers[
            "Pragma"
        ] = "no-cache"

        response.headers[
            "X-Robots-Tag"
        ] = "noindex,nofollow,noarchive"

    return response


# ============================================================
# ERRORS
# ============================================================

@app.errorhandler(403)
def forbidden(error):

    return public_page(
        "Access Denied",
        """
<div class="card">

<h1>
Access Denied
</h1>

<p>
You do not have permission to access this page.
</p>

<a class="btn"
href="/">
Return Home
</a>

</div>
"""
    ), 403


@app.errorhandler(404)
def not_found(error):

    return public_page(
        "Page Not Found",
        """
<div class="card">

<h1>
Page Not Found
</h1>

<p>
The requested page does not exist.
</p>

<a class="btn"
href="/">
Return Home
</a>

</div>
"""
    ), 404


# ============================================================
# ROBOTS
# ============================================================

@app.route("/robots.txt")
def robots():

    response = make_response(
"""User-agent: *
Allow: /
Disallow: /admin
Disallow: /student
Disallow: /ask
Disallow: /research
Disallow: /logout
"""
    )

    response.headers[
        "Content-Type"
    ] = "text/plain"

    return response


# ============================================================
# SITEMAP
# ============================================================

@app.route("/sitemap.xml")
def sitemap():

    base = request.url_root.rstrip("/")

    xml = f"""<?xml version="1.0"
encoding="UTF-8"?>

<urlset
xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">

<url>
<loc>{base}/</loc>
</url>

<url>
<loc>{base}/login</loc>
</url>

<url>
<loc>{base}/register</loc>
</url>

</urlset>
"""

    response = make_response(
        xml
    )

    response.headers[
        "Content-Type"
    ] = "application/xml"

    return response


# ============================================================
# HEALTH CHECK
# ============================================================

@app.route("/health")
def health():

    if not supabase_configured():

        return {
            "status": "error",
            "supabase": False
        }, 503

    try:

        supabase_get(
            "profiles",
            {
                "select": "id",
                "limit": "1"
            }
        )

        return {
            "status": "ok",
            "supabase": True
        }

    except Exception as exc:

        return {
            "status": "error",
            "supabase": False,
            "message": str(exc)
        }, 503


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            "9999"
        )
    )

    print("=" * 60)
    print("KOJA AFRICA")
    print("Knowledge • Questions • Answers")
    print("SUPABASE EDITION")
    print("=" * 60)

    if not SUPABASE_URL:

        print(
            "WARNING: SUPABASE_URL is not configured."
        )

    if not SUPABASE_SERVICE_KEY:

        print(
            "WARNING: SUPABASE_SERVICE_KEY is not configured."
        )

    print(
        f"Server: http://0.0.0.0:{port}"
    )

    print("=" * 60)

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )

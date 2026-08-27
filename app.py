import os
import io
import uuid
import secrets
import logging
from functools import wraps
from datetime import datetime, timezone

import requests

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
    jsonify,
)

from werkzeug.utils import secure_filename

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.units import mm


# ============================================================
# KOJA AFRICA
# FLASK + SUPABASE
# UPDATED TO MATCH USER'S SUPPLIED TABLES
# ============================================================

app = Flask(__name__)

app.secret_key = os.environ.get(
    "KOJA_SECRET_KEY",
    secrets.token_hex(32)
)

app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024


# ============================================================
# ENVIRONMENT
# ============================================================

SUPABASE_URL = os.environ.get(
    "SUPABASE_URL",
    ""
).rstrip("/")

SUPABASE_SERVICE_KEY = os.environ.get(
    "SUPABASE_SERVICE_KEY",
    ""
)

STORAGE_BUCKET = os.environ.get(
    "KOJA_STORAGE_BUCKET",
    "koja-files"
)

ADMIN_EMAIL = os.environ.get(
    "KOJA_ADMIN_EMAIL",
    ""
).strip().lower()

ADMIN_PASSWORD = os.environ.get(
    "KOJA_ADMIN_PASSWORD",
    ""
)

APP_NAME = "KOJA AFRICA"
APP_TAGLINE = "Knowledge • Questions • Answers"


# ============================================================
# FILE TYPES
# ============================================================

ALLOWED_EXTENSIONS = {
    "pdf",
    "doc",
    "docx",
    "xls",
    "xlsx",
    "txt",
    "csv",
    "ppt",
    "pptx",
}


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(level=logging.INFO)

logger = logging.getLogger("koja")


# ============================================================
# GENERAL HELPERS
# ============================================================

def now_iso():
    return datetime.now(timezone.utc).isoformat()


def safe_text(value, limit=50000):
    if value is None:
        return ""

    return str(value).strip()[:limit]


def allowed_file(filename):
    if not filename:
        return False

    if "." not in filename:
        return False

    extension = filename.rsplit(".", 1)[1].lower()

    return extension in ALLOWED_EXTENSIONS


def current_user():
    return session.get("user")


def current_user_id():
    user = current_user()

    if not user:
        return None

    return user.get("id")


def current_user_email():
    user = current_user()

    if not user:
        return None

    return user.get("email")


def is_admin():
    user = current_user()

    return bool(
        user and
        user.get("role") == "admin"
    )


# ============================================================
# AUTH DECORATORS
# ============================================================

def login_required(fn):

    @wraps(fn)
    def wrapper(*args, **kwargs):

        if not current_user():

            flash("Please log in first.")

            return redirect(
                url_for("login")
            )

        return fn(*args, **kwargs)

    return wrapper


def admin_required(fn):

    @wraps(fn)
    def wrapper(*args, **kwargs):

        if not is_admin():

            flash("Administrator access required.")

            return redirect(
                url_for("login")
            )

        return fn(*args, **kwargs)

    return wrapper


def student_required(fn):

    @wraps(fn)
    def wrapper(*args, **kwargs):

        if not current_user():

            return redirect(
                url_for("login")
            )

        if is_admin():

            return redirect(
                url_for("admin_dashboard")
            )

        return fn(*args, **kwargs)

    return wrapper


# ============================================================
# CSRF
# ============================================================

def csrf_token():

    if "csrf_token" not in session:

        session["csrf_token"] = secrets.token_urlsafe(32)

    return session["csrf_token"]


def csrf_check():

    supplied = request.form.get(
        "csrf_token",
        ""
    )

    stored = session.get(
        "csrf_token",
        ""
    )

    if not supplied or not stored:
        return False

    return secrets.compare_digest(
        supplied,
        stored
    )


@app.context_processor
def inject_globals():

    return {
        "csrf_token": csrf_token(),
        "koja_user": current_user(),
        "is_admin": is_admin(),
    }


# ============================================================
# SUPABASE REST
# ============================================================

def require_supabase():

    if not SUPABASE_URL:
        raise RuntimeError(
            "SUPABASE_URL is missing."
        )

    if not SUPABASE_SERVICE_KEY:
        raise RuntimeError(
            "SUPABASE_SERVICE_KEY is missing."
        )


def sb_headers(extra=None):

    require_supabase()

    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": (
            f"Bearer {SUPABASE_SERVICE_KEY}"
        ),
        "Content-Type": "application/json",
    }

    if extra:
        headers.update(extra)

    return headers


def sb_request(
    method,
    table,
    params=None,
    data=None,
    prefer=None,
    timeout=30
):

    require_supabase()

    headers = sb_headers()

    if prefer:
        headers["Prefer"] = prefer

    response = requests.request(
        method,
        f"{SUPABASE_URL}/rest/v1/{table}",
        headers=headers,
        params=params,
        json=data,
        timeout=timeout,
    )

    if not response.ok:

        logger.error(
            "Supabase error %s %s: %s",
            method,
            table,
            response.text,
        )

    return response


def db_select(
    table,
    params=None
):

    response = sb_request(
        "GET",
        table,
        params=params,
    )

    if not response.ok:

        raise RuntimeError(
            response.text
        )

    if not response.text:

        return []

    return response.json()


def db_insert(
    table,
    data,
    select="*"
):

    response = sb_request(
        "POST",
        table,
        params={
            "select": select
        },
        data=data,
        prefer="return=representation",
    )

    if not response.ok:

        raise RuntimeError(
            response.text
        )

    if not response.text:

        return []

    return response.json()


def db_update(
    table,
    filters,
    data,
    select="*"
):

    params = dict(filters)

    params["select"] = select

    response = sb_request(
        "PATCH",
        table,
        params=params,
        data=data,
        prefer="return=representation",
    )

    if not response.ok:

        raise RuntimeError(
            response.text
        )

    if not response.text:

        return []

    return response.json()


def db_delete(
    table,
    filters
):

    response = sb_request(
        "DELETE",
        table,
        params=filters,
        prefer="return=minimal",
    )

    if not response.ok:

        raise RuntimeError(
            response.text
        )

    return True


# ============================================================
# SUPABASE AUTH
# ============================================================

def auth_headers():

    require_supabase()

    return {
        "apikey": SUPABASE_SERVICE_KEY,
        "Content-Type": "application/json",
    }


def auth_signup(
    email,
    password,
    name
):

    return requests.post(
        f"{SUPABASE_URL}/auth/v1/signup",
        headers=auth_headers(),
        json={
            "email": email,
            "password": password,
            "data": {
                "name": name
            },
        },
        timeout=30,
    )


def auth_login(
    email,
    password
):

    return requests.post(
        f"{SUPABASE_URL}/auth/v1/token"
        "?grant_type=password",
        headers=auth_headers(),
        json={
            "email": email,
            "password": password,
        },
        timeout=30,
    )


def auth_recover(email):

    return requests.post(
        f"{SUPABASE_URL}/auth/v1/recover",
        headers=auth_headers(),
        json={
            "email": email
        },
        timeout=30,
    )


def auth_users():

    response = requests.get(
        f"{SUPABASE_URL}/auth/v1/admin/users",
        headers=sb_headers(),
        params={
            "page": 1,
            "per_page": 1000,
        },
        timeout=30,
    )

    if not response.ok:

        raise RuntimeError(
            response.text
        )

    data = response.json()

    return data.get(
        "users",
        []
    )


def auth_update_user_metadata(
    access_token,
    name
):

    return requests.put(
        f"{SUPABASE_URL}/auth/v1/user",
        headers={
            "apikey": SUPABASE_SERVICE_KEY,
            "Authorization": (
                f"Bearer {access_token}"
            ),
            "Content-Type": "application/json",
        },
        json={
            "data": {
                "name": name
            }
        },
        timeout=30,
    )


# ============================================================
# STORAGE
# ============================================================

def storage_upload(
    data,
    path,
    content_type
):

    require_supabase()

    path = path.lstrip("/")

    response = requests.post(
        f"{SUPABASE_URL}/storage/v1/object/"
        f"{STORAGE_BUCKET}/{path}",
        headers={
            "Authorization": (
                f"Bearer {SUPABASE_SERVICE_KEY}"
            ),
            "apikey": SUPABASE_SERVICE_KEY,
            "Content-Type": (
                content_type or
                "application/octet-stream"
            ),
            "x-upsert": "true",
        },
        data=data,
        timeout=90,
    )

    if not response.ok:

        raise RuntimeError(
            "Storage upload failed: "
            + response.text
        )

    return path


def storage_download(path):

    require_supabase()

    if not path:

        raise RuntimeError(
            "Missing storage path."
        )

    path = path.lstrip("/")

    response = requests.get(
        f"{SUPABASE_URL}/storage/v1/object/"
        f"{STORAGE_BUCKET}/{path}",
        headers={
            "Authorization": (
                f"Bearer {SUPABASE_SERVICE_KEY}"
            ),
            "apikey": SUPABASE_SERVICE_KEY,
        },
        timeout=90,
    )

    if not response.ok:

        raise RuntimeError(
            "Storage download failed: "
            + response.text
        )

    return response.content


# ============================================================
# RECORD HELPERS
# ============================================================

def get_assignment(aid):

    rows = db_select(
        "assignments",
        {
            "id": f"eq.{aid}",
            "select": "*",
            "limit": "1",
        },
    )

    return rows[0] if rows else None


def get_answer_for_assignment(aid):

    rows = db_select(
        "assignment_answers",
        {
            "assignment_id": f"eq.{aid}",
            "select": "*",
            "order": "created_at.desc",
            "limit": "1",
        },
    )

    return rows[0] if rows else None


def get_question_answer(qid):

    rows = db_select(
        "answers",
        {
            "question_id": f"eq.{qid}",
            "select": "*",
            "order": "created_at.desc",
            "limit": "1",
        },
    )

    return rows[0] if rows else None


def get_document(did):

    rows = db_select(
        "document_library",
        {
            "id": f"eq.{did}",
            "select": "*",
            "limit": "1",
        },
    )

    return rows[0] if rows else None


# ============================================================
# DOCUMENT ACCESS LOG
# ============================================================

def access_log(
    document_id,
    action
):

    try:

        db_insert(
            "document_access_logs",
            {
                "id": str(uuid.uuid4()),
                "document_id": document_id,
                "user_id": current_user_id(),
                "action": action,
                "created_at": now_iso(),
            },
        )

    except Exception:

        logger.exception(
            "Could not write document access log."
        )


# ============================================================
# DOCUMENT RECORD
# ============================================================

def record_document_action(
    document_id,
    action
):

    try:

        db_insert(
            "document_records",
            {
                "id": str(uuid.uuid4()),
                "document_id": document_id,
                "user_id": current_user_id(),
                "action": action,
                "ip_address": request.headers.get(
                    "X-Forwarded-For",
                    request.remote_addr,
                ),
                "user_agent": (
                    request.headers.get(
                        "User-Agent",
                        ""
                    )[:1000]
                ),
                "created_at": now_iso(),
            },
        )

    except Exception:

        logger.exception(
            "Could not write document record."
        )


# ============================================================
# FIRST OPEN LOG
# ============================================================

@app.before_request
def first_open_log():

    ignored = {
        "static",
        "health",
        "home",
        "login",
        "register",
        "forgot_password",
    }

    if request.endpoint in ignored:
        return

    if not current_user():
        return

    if session.get(
        "web_open_logged"
    ):
        return

    session["web_open_logged"] = True

    try:

        record_document_action(
            None,
            "web_open",
        )

    except Exception:

        logger.exception(
            "First-open logging failed."
        )


# ============================================================
# KOJA BRAIN SCREEN SYMBOL
# SCREEN ONLY
# ============================================================

BRAIN_LOGO = """
<div class="koja-mark"
     aria-label="KOJA AFRICA"
     title="KOJA AFRICA">

<svg viewBox="0 0 120 90">

<path d="
M48 15
c-14-8-31 2-31 18
c0 4 1 8 3 11
c-9 8-5 24 7 28
c5 2 10 2 15 0
c5 7 15 9 23 5
c4 8 13 11 21 7
c9-4 12-14 8-23
c7-4 9-13 5-20
c5-8-1-15-7-18
c-2-5-6-9-12-12z"

fill="none"
stroke="currentColor"
stroke-width="4"
stroke-linecap="round"
stroke-linejoin="round"/>

<path d="
M48 18v53
M35 27c6 2 10 7 10 14
M24 45c8 0 14 4 17 10
M72 22c-5 3-8 8-8 14
M82 38c-8 1-13 6-15 13
M73 61c-5-1-10 1-13 5"

fill="none"
stroke="currentColor"
stroke-width="3"
stroke-linecap="round"/>

</svg>

<span>KOJA</span>

</div>
"""


# ============================================================
# CLEAN PDF GENERATOR
# NO KOJA BRAIN / WATERMARK
# ============================================================

def build_pdf(
    title,
    subject,
    student_name,
    question,
    answer
):

    output = io.BytesIO()

    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "KOJA_Title",
        parent=styles["Title"],
        alignment=TA_CENTER,
        fontSize=18,
        leading=22,
        spaceAfter=12,
    )

    body_style = ParagraphStyle(
        "KOJA_Body",
        parent=styles["BodyText"],
        fontSize=10.5,
        leading=15,
        spaceAfter=8,
    )

    heading_style = ParagraphStyle(
        "KOJA_Heading",
        parent=styles["Heading2"],
        fontSize=12,
        leading=16,
        spaceBefore=8,
        spaceAfter=6,
    )

    def clean(value):

        value = safe_text(value)

        return (
            value
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("\n", "<br/>")
        )

    story = [

        Paragraph(
            "ANSWERED ASSIGNMENT",
            title_style
        ),

        Paragraph(
            f"<b>Assignment:</b> "
            f"{clean(title)}",
            body_style
        ),

        Paragraph(
            f"<b>Subject:</b> "
            f"{clean(subject)}",
            body_style
        ),

        Paragraph(
            f"<b>Student:</b> "
            f"{clean(student_name)}",
            body_style
        ),

        Paragraph(
            "QUESTION",
            heading_style
        ),

        Paragraph(
            clean(question),
            body_style
        ),

        Paragraph(
            "ANSWER",
            heading_style
        ),

        Paragraph(
            clean(answer),
            body_style
        ),

        Spacer(
            1,
            15
        ),

        Paragraph(
            "Generated academic document",
            ParagraphStyle(
                "Footer",
                parent=body_style,
                alignment=TA_CENTER,
                fontSize=8,
            ),
        ),
    ]

    document.build(story)

    return output.getvalue()


# ============================================================
# BASE TEMPLATE
# ============================================================

BASE = """

<!doctype html>

<html>

<head>

<meta charset="utf-8">

<meta name="viewport"
      content="width=device-width,initial-scale=1">

<title>
{{ title }} - KOJA AFRICA
</title>

<style>

:root{

--bg:#f3f6fa;

--card:#ffffff;

--text:#172033;

--muted:#667085;

--nav:#08284a;

--accent:#1261a0;

--border:#dce3ec;

--success:#218c5a;

--danger:#b42318;

}

body.dark{

--bg:#0d141d;

--card:#17212c;

--text:#f4f7fa;

--muted:#aab6c5;

--border:#2d3b4d;

--nav:#061a30;

}

*{

box-sizing:border-box;

}

body{

margin:0;

background:var(--bg);

color:var(--text);

font-family:
Arial,
Helvetica,
sans-serif;

transition:
background .2s,
color .2s;

}

nav{

background:var(--nav);

color:#fff;

position:sticky;

top:0;

z-index:100;

box-shadow:
0 2px 12px
rgba(0,0,0,.15);

}

.navinner{

max-width:1200px;

margin:auto;

padding:
10px 15px;

display:flex;

align-items:center;

gap:14px;

flex-wrap:wrap;

}

.brand{

font-weight:900;

font-size:20px;

margin-right:auto;

letter-spacing:.3px;

}

nav a{

color:#fff;

text-decoration:none;

font-size:14px;

padding:6px 4px;

}

nav a:hover{

opacity:.8;

}

.container{

max-width:1200px;

margin:
24px auto;

padding:
0 15px;

}

.card{

background:var(--card);

border:
1px solid var(--border);

border-radius:15px;

padding:20px;

margin-bottom:18px;

box-shadow:
0 5px 18px
rgba(0,0,0,.05);

}

.grid{

display:grid;

grid-template-columns:
repeat(
auto-fit,
minmax(220px,1fr)
);

gap:15px;

}

input,
textarea,
select{

width:100%;

padding:11px;

margin:
6px 0 13px;

border:
1px solid var(--border);

border-radius:9px;

background:var(--card);

color:var(--text);

font-size:15px;

}

textarea{

min-height:140px;

resize:vertical;

}

button,
.btn{

display:inline-block;

padding:
10px 15px;

border:0;

border-radius:9px;

background:var(--accent);

color:#fff;

text-decoration:none;

cursor:pointer;

font-size:14px;

}

.btn-success{

background:var(--success);

}

.btn-danger{

background:var(--danger);

}

.btn-dark{

background:#172033;

}

.flash{

background:#fff3cd;

color:#5b4700;

padding:12px;

border-radius:9px;

margin-bottom:15px;

}

body.dark .flash{

background:#4b3d14;

color:#fff0ad;

}

table{

width:100%;

border-collapse:collapse;

}

th,
td{

padding:10px;

border-bottom:
1px solid var(--border);

text-align:left;

vertical-align:top;

}

.answer{

white-space:pre-wrap;

line-height:1.65;

}

.small{

font-size:13px;

color:var(--muted);

}

.hero{

text-align:center;

padding:
35px 10px;

}

.koja-mark{

display:inline-flex;

align-items:center;

gap:8px;

color:#1261a0;

font-weight:900;

font-size:22px;

letter-spacing:2px;

}

.koja-mark svg{

width:58px;

height:48px;

}

.screen-mark{

position:fixed;

right:14px;

bottom:14px;

opacity:.17;

z-index:1;

pointer-events:none;

}

.stat{

font-size:30px;

font-weight:800;

}

.badge{

display:inline-block;

padding:
5px 9px;

border-radius:999px;

background:#e7eef7;

font-size:12px;

}

body.dark .badge{

background:#29384a;

}

.actions{

display:flex;

gap:8px;

flex-wrap:wrap;

}

.status-submitted{

background:#fff1c2;

}

.status-assigned{

background:#dceeff;

}

.status-reviewing{

background:#e3ddff;

}

.status-answered{

background:#d8f5e5;

}

.status-completed{

background:#d8f5e5;

}

.status-rejected{

background:#ffe0df;

}

.file-box{

border:
1px dashed var(--border);

border-radius:10px;

padding:15px;

margin-top:12px;

}

@media(max-width:700px){

.container{

margin-top:15px;

}

table{

font-size:12px;

display:block;

overflow-x:auto;

}

nav a{

font-size:13px;

}

}

</style>

</head>

<body>

<nav>

<div class="navinner">

<span class="brand">
KOJA AFRICA
</span>

{% if koja_user %}

<a href="{{ url_for('dashboard') }}">
Dashboard
</a>

<a href="{{ url_for('documents') }}">
Library
</a>

{% if is_admin %}

<a href="{{ url_for('admin_assignments') }}">
Assignments
</a>

<a href="{{ url_for('admin_documents') }}">
Resources
</a>

<a href="{{ url_for('admin_logs') }}">
Logs
</a>

{% endif %}

<a href="{{ url_for('settings') }}">
Settings
</a>

<a href="{{ url_for('logout') }}">
Logout
</a>

{% else %}

<a href="{{ url_for('login') }}">
Login
</a>

<a href="{{ url_for('register') }}">
Create Account
</a>

{% endif %}

</div>

</nav>


<div class="screen-mark">

{{ brain|safe }}

</div>


<div class="container">

{% with messages =
get_flashed_messages() %}

{% for message in messages %}

<div class="flash">

{{ message }}

</div>

{% endfor %}

{% endwith %}

{{ content|safe }}

</div>


<script>

(function(){

const dark =
localStorage.getItem(
"koja_dark"
) === "1";

if(dark){

document.body.classList.add(
"dark"
);

}

})();


function toggleDark(){

document.body.classList.toggle(
"dark"
);

localStorage.setItem(
"koja_dark",
document.body.classList.contains(
"dark"
) ? "1" : "0"
);

}

</script>

</body>

</html>

"""


def page(
    content,
    title="KOJA AFRICA"
):

    return render_template_string(
        BASE,
        content=content,
        title=title,
        brain=BRAIN_LOGO,
    )


# ============================================================
# HOME
# ============================================================

@app.route("/")
def home():

    return page(
        f"""

<div class="hero">

{BRAIN_LOGO}

<h1>
KOJA AFRICA
</h1>

<p>
Knowledge • Questions • Answers
</p>

<p class="small">
Assignments • Past Papers • Notes • Books
• Academic Resources
</p>

<div class="actions"
     style="justify-content:center">

<a class="btn"
   href="/login">

Login

</a>

<a class="btn btn-dark"
   href="/register">

Create Account

</a>

</div>

</div>


<div class="grid">

<div class="card">

<h3>
Assignments
</h3>

<p>
Submit assignments or receive assignments
directly from an administrator.
</p>

</div>


<div class="card">

<h3>
Learning Library
</h3>

<p>
Past papers, notes, books and other
academic resources.
</p>

</div>


<div class="card">

<h3>
Comments & Status
</h3>

<p>
Track assignment progress and communicate
through comments and responses.
</p>

</div>


<div class="card">

<h3>
Secure Files
</h3>

<p>
Documents are delivered through KOJA
rather than exposing storage paths.
</p>

</div>

</div>

""",
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

        if not csrf_check():
            abort(400)

        name = safe_text(
            request.form.get("name"),
            255
        )

        email = safe_text(
            request.form.get("email"),
            255
        ).lower()

        password = request.form.get(
            "password",
            ""
        )

        if (
            not name
            or not email
            or len(password) < 6
        ):

            flash(
                "Enter your name, email and a password "
                "of at least 6 characters."
            )

            return redirect(
                url_for("register")
            )

        try:

            response = auth_signup(
                email,
                password,
                name,
            )

            if not response.ok:

                flash(
                    "Registration failed."
                )

                logger.error(
                    response.text
                )

                return redirect(
                    url_for("register")
                )

            data = response.json()

            user = data.get(
                "user"
            )

            if (
                data.get("access_token")
                and user
            ):

                session.clear()

                session["user"] = {
                    "id": user.get("id"),
                    "email": user.get(
                        "email",
                        email
                    ),
                    "student_name": name,
                    "role": "student",
                    "access_token": data.get(
                        "access_token"
                    ),
                }

                session[
                    "web_open_logged"
                ] = False

                flash(
                    "Account created successfully."
                )

                return redirect(
                    url_for("dashboard")
                )

            flash(
                "Account created. Check your email "
                "if email confirmation is enabled."
            )

            return redirect(
                url_for("login")
            )

        except Exception as error:

            logger.exception(error)

            flash(
                "Registration could not be completed."
            )

    return page(
        """

<div class="card"
     style="max-width:600px;margin:auto">

<h2>
Create Student Account
</h2>

<form method="post">

<input
type="hidden"
name="csrf_token"
value="{{ csrf_token }}"
>

<label>
Name
</label>

<input
name="name"
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
Password
</label>

<input
type="password"
name="password"
minlength="6"
required
>

<button>
Create Account
</button>

</form>

</div>

""",
        "Register"
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

        if not csrf_check():
            abort(400)

        email = safe_text(
            request.form.get("email"),
            255
        ).lower()

        password = request.form.get(
            "password",
            ""
        )

        # ----------------------------------------------------
        # SERVER-SIDE ADMIN ACCOUNT
        # ----------------------------------------------------

        if (
            ADMIN_EMAIL
            and ADMIN_PASSWORD
            and email == ADMIN_EMAIL
            and secrets.compare_digest(
                password,
                ADMIN_PASSWORD
            )
        ):

            session.clear()

            session["user"] = {
                "id": None,
                "email": ADMIN_EMAIL,
                "student_name": "Administrator",
                "role": "admin",
            }

            session[
                "web_open_logged"
            ] = False

            flash(
                "Administrator login successful."
            )

            return redirect(
                url_for("admin_dashboard")
            )

        try:

            response = auth_login(
                email,
                password,
            )

            if not response.ok:

                flash(
                    "Login failed. Check your email "
                    "and password."
                )

                return redirect(
                    url_for("login")
                )

            data = response.json()

            user = data.get(
                "user",
                {}
            )

            metadata = (
                user.get(
                    "user_metadata"
                )
                or {}
            )

            session.clear()

            session["user"] = {
                "id": user.get("id"),
                "email": user.get(
                    "email",
                    email
                ),
                "student_name": (
                    metadata.get("name")
                    or email.split("@")[0]
                ),
                "role": "student",
                "access_token": data.get(
                    "access_token"
                ),
            }

            session[
                "web_open_logged"
            ] = False

            return redirect(
                url_for("dashboard")
            )

        except Exception as error:

            logger.exception(error)

            flash(
                "Login could not be completed."
            )

    return page(
        """

<div class="card"
     style="max-width:600px;margin:auto">

<h2>
Login
</h2>

<form method="post">

<input
type="hidden"
name="csrf_token"
value="{{ csrf_token }}"
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
Password
</label>

<input
type="password"
name="password"
required
>

<button>
Login
</button>

</form>

<p>

<a href="/forgot-password">
Forgot Password?
</a>

</p>

</div>

""",
        "Login"
    )


# ============================================================
# FORGOT PASSWORD
# ============================================================

@app.route(
    "/forgot-password",
    methods=["GET", "POST"]
)
def forgot_password():

    if request.method == "POST":

        if not csrf_check():
            abort(400)

        email = safe_text(
            request.form.get("email"),
            255
        ).lower()

        if not email:

            flash(
                "Enter your account email."
            )

            return redirect(
                url_for("forgot_password")
            )

        try:

            response = auth_recover(
                email
            )

            # Deliberately don't expose account existence.

            if not response.ok:

                logger.warning(
                    "Recovery request response: %s",
                    response.text,
                )

            flash(
                "If the account exists, "
                "Supabase will send password "
                "recovery instructions."
            )

            return redirect(
                url_for("login")
            )

        except Exception as error:

            logger.exception(error)

            flash(
                "Password recovery request failed."
            )

    return page(
        """

<div class="card"
     style="max-width:600px;margin:auto">

<h2>
Forgot Password
</h2>

<p class="small">

Enter your registered email address.
Supabase will handle the recovery process.

</p>

<form method="post">

<input
type="hidden"
name="csrf_token"
value="{{ csrf_token }}"
>

<input
type="email"
name="email"
required
>

<button>
Send Reset Instructions
</button>

</form>

</div>

""",
        "Forgot Password"
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
# SETTINGS
# ============================================================

@app.route(
    "/settings",
    methods=["GET", "POST"]
)
@login_required
def settings():

    user = current_user()

    if request.method == "POST":

        if not csrf_check():
            abort(400)

        name = safe_text(
            request.form.get("name"),
            255
        )

        if (
            name
            and not is_admin()
            and user.get("access_token")
        ):

            try:

                response = auth_update_user_metadata(
                    user.get("access_token"),
                    name,
                )

                if response.ok:

                    session[
                        "user"
                    ][
                        "student_name"
                    ] = name

                    flash(
                        "Profile updated successfully."
                    )

                else:

                    flash(
                        "Could not update profile."
                    )

            except Exception:

                logger.exception(
                    "Profile update failed."
                )

                flash(
                    "Could not update profile."
                )

    return page(
        f"""

<div class="card"
     style="max-width:700px;margin:auto">

<h2>
Settings
</h2>

<p>
<b>Name:</b>
{safe_text(user.get("student_name"))}
</p>

<p>
<b>Email:</b>
{safe_text(user.get("email"))}
</p>

<form method="post">

<input
type="hidden"
name="csrf_token"
value="{{{{ csrf_token }}}}"
>

<label>
Display Name
</label>

<input
name="name"
value="{safe_text(user.get('student_name'))}"
>

<button>
Save Profile
</button>

</form>

<hr>

<h3>
Appearance
</h3>

<button
type="button"
onclick="toggleDark()">

Toggle Dark Mode

</button>

<p class="small">

Dark mode is saved on this device.

</p>

</div>

""",
        "Settings"
    )


# ============================================================
# STUDENT DASHBOARD
# ============================================================

@app.route("/dashboard")
@login_required
def dashboard():

    if is_admin():

        return redirect(
            url_for("admin_dashboard")
        )

    uid = current_user_id()

    email = current_user_email()

    try:

        assignments = db_select(
            "assignments",
            {
                "or": (
                    f"student_id.eq.{uid},"
                    f"email.eq.{email}"
                ),
                "select": "*",
                "order": "created_at.desc",
            },
        )

    except Exception:

        logger.exception(
            "Could not load assignments."
        )

        assignments = []

    rows = ""

    for assignment in assignments:

        answer = get_answer_for_assignment(
            assignment["id"]
        )

        answer_button = ""

        if (
            answer
            and answer.get(
                "answer_file_path"
            )
        ):

            answer_button = (
                f'<a class="btn btn-success" '
                f'href="/assignment/'
                f'{assignment["id"]}'
                f'/answer/download">'
                f'Answer PDF</a>'
            )

        rows += f"""

<tr>

<td>
{safe_text(assignment.get("title"))}
</td>

<td>
{safe_text(assignment.get("subject"))}
</td>

<td>
<span class="badge">
{safe_text(assignment.get("status"))}
</span>
</td>

<td>
{safe_text(
    assignment.get("admin_comment")
) or "—"}
</td>

<td>

<div class="actions">

<a class="btn"
href="/assignment/{assignment["id"]}">

View

</a>

{answer_button}

</div>

</td>

</tr>

"""

    return page(
        f"""

<div class="card">

<h2>
Student Dashboard
</h2>

<p>
Welcome,
<b>
{safe_text(
    current_user().get(
        "student_name"
    )
)}
</b>
</p>

<div class="actions">

<a class="btn"
href="/assignment/upload">

Upload Assignment

</a>

<a class="btn btn-dark"
href="/documents">

Learning Library

</a>

<a class="btn"
href="/student/document/upload">

Upload Resource

</a>

<a class="btn"
href="/settings">

Settings

</a>

</div>

</div>


<div class="card">

<h3>
My Assignments
</h3>

<table>

<tr>

<th>
Title
</th>

<th>
Subject
</th>

<th>
Status
</th>

<th>
Comment
</th>

<th>
Actions
</th>

</tr>

{rows or
"<tr><td colspan='5'>No assignments yet.</td></tr>"}

</table>

</div>

""",
        "Student Dashboard"
    )


# ============================================================
# STUDENT ASSIGNMENT UPLOAD
# ============================================================

@app.route(
    "/assignment/upload",
    methods=["GET", "POST"]
)
@student_required
def upload_assignment():

    if request.method == "POST":

        if not csrf_check():
            abort(400)

        title = safe_text(
            request.form.get("title"),
            255
        )

        description = safe_text(
            request.form.get("description"),
            5000
        )

        subject = safe_text(
            request.form.get("subject"),
            255
        )

        course = safe_text(
            request.form.get("course"),
            255
        )

        level = safe_text(
            request.form.get("class_level"),
            255
        )

        question = safe_text(
            request.form.get("question"),
            15000
        )

        file = request.files.get(
            "file"
        )

        if (
            not title
            or not file
            or not file.filename
            or not allowed_file(
                file.filename
            )
        ):

            flash(
                "Title and a supported file are required."
            )

            return redirect(
                url_for(
                    "upload_assignment"
                )
            )

        try:

            data = file.read()

            assignment_id = str(
                uuid.uuid4()
            )

            filename = secure_filename(
                file.filename
            )

            path = (
                f"assignments/"
                f"{assignment_id}/"
                f"{filename}"
            )

            mime = (
                file.content_type
                or "application/octet-stream"
            )

            storage_upload(
                data,
                path,
                mime,
            )

            user = current_user()

            db_insert(
                "assignments",
                {
                    "id": assignment_id,
                    "student_id": user.get("id"),
                    "title": title,
                    "description": description,
                    "subject": subject,
                    "course": course,
                    "class_level": level,
                    "file_name": filename,
                    "file_path": path,
                    "file_size": len(data),
                    "mime_type": mime,
                    "status": "submitted",
                    "email": user.get("email"),
                    "question": question,
                    "student_name": user.get(
                        "student_name"
                    ),
                    "created_at": now_iso(),
                    "updated_at": now_iso(),
                },
            )

            flash(
                "Assignment uploaded successfully."
            )

            return redirect(
                url_for("dashboard")
            )

        except Exception as error:

            logger.exception(error)

            flash(
                "Assignment upload failed."
            )

    return page(
        """

<div class="card">

<h2>
Upload Assignment
</h2>

<form
method="post"
enctype="multipart/form-data">

<input
type="hidden"
name="csrf_token"
value="{{ csrf_token }}"
>

<label>
Title
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
>

<label>
Course
</label>

<input
name="course"
>

<label>
Class Level
</label>

<input
name="class_level"
>

<label>
Description
</label>

<textarea
name="description">
</textarea>

<label>
Question / Instructions
</label>

<textarea
name="question">
</textarea>

<label>
PDF / Word / Academic File
</label>

<input
type="file"
name="file"
required
>

<button>
Upload Assignment
</button>

</form>

</div>

""",
        "Upload Assignment"
    )


# ============================================================
# VIEW ASSIGNMENT
# ============================================================

@app.route(
    "/assignment/<aid>"
)
@login_required
def view_assignment(aid):

    assignment = get_assignment(
        aid
    )

    if not assignment:
        abort(404)

    user = current_user()

    if (
        not is_admin()
        and assignment.get(
            "email"
        ) != user.get("email")
        and assignment.get(
            "student_id"
        ) != user.get("id")
    ):

        abort(403)

    answer = get_answer_for_assignment(
        aid
    )

    try:

        comments = db_select(
            "assignment_responses",
            {
                "assignment_id":
                    f"eq.{aid}",
                "select": "*",
                "order":
                    "created_at.desc",
            },
        )

    except Exception:

        comments = []

    comments_html = ""

    for comment in comments:

        comments_html += f"""

<div class="file-box">

<b>
Response
</b>

<p class="answer">

{safe_text(
    comment.get(
        "response_text"
    )
)}

</p>

<span class="small">

{safe_text(
    comment.get(
        "created_at"
    )
)}

</span>

</div>

"""

    answer_html = ""

    if answer:

        download_button = ""

        if answer.get(
            "answer_file_path"
        ):

            download_button = f"""

<a class="btn btn-success"
href="/assignment/{aid}/answer/download">

Download Answer PDF

</a>

"""

        answer_html = f"""

<div class="card">

<h3>
Answer
</h3>

<div class="answer">

{safe_text(
    answer.get(
        "answer_text"
    )
)}

</div>

<br>

{download_button}

</div>

"""

    return page(
        f"""

<div class="card">

<h2>
{safe_text(
    assignment.get("title")
)}
</h2>

<p>

<b>Status:</b>

<span class="badge">

{safe_text(
    assignment.get("status")
)}

</span>

</p>

<p>

<b>Subject:</b>
{safe_text(
    assignment.get("subject")
)}

</p>

<p>

<b>Course:</b>
{safe_text(
    assignment.get("course")
)}

</p>

<p>

<b>Class:</b>
{safe_text(
    assignment.get("class_level")
)}

</p>

<p>

<b>Admin Comment:</b>

{safe_text(
    assignment.get(
        "admin_comment"
    )
) or "No comment yet."}

</p>

<h3>
Question
</h3>

<div class="answer">

{safe_text(
    assignment.get(
        "question"
    )
    or
    assignment.get(
        "description"
    )
)}

</div>

<br>

<a class="btn"
href="/assignment/{aid}/download">

Download Assignment

</a>

</div>


{answer_html}


<div class="card">

<h3>
Comments & Responses
</h3>

{comments_html or
"<p>No responses yet.</p>"}

</div>

""",
        "Assignment"
    )


# ============================================================
# STUDENT COMMENT / RESPONSE
# ============================================================

@app.route(
    "/assignment/<aid>/comment",
    methods=["POST"]
)
@login_required
def student_assignment_comment(aid):

    if not csrf_check():
        abort(400)

    assignment = get_assignment(
        aid
    )

    if not assignment:
        abort(404)

    user = current_user()

    if (
        not is_admin()
        and assignment.get(
            "student_id"
        ) != user.get("id")
        and assignment.get(
            "email"
        ) != user.get("email")
    ):

        abort(403)

    text = safe_text(
        request.form.get(
            "response_text"
        ),
        10000
    )

    if not text:

        flash(
            "Comment cannot be empty."
        )

        return redirect(
            url_for(
                "view_assignment",
                aid=aid
            )
        )

    try:

        db_insert(
            "assignment_responses",
            {
                "id": str(uuid.uuid4()),
                "assignment_id": aid,
                "admin_id": None,
                "response_text": text,
                "created_at": now_iso(),
                "file_name": None,
                "file_path": None,
                "file_size": 0,
                "mime_type": None,
            },
        )

        flash(
            "Comment submitted."
        )

    except Exception as error:

        logger.exception(error)

        flash(
            "Could not submit comment."
        )

    return redirect(
        url_for(
            "view_assignment",
            aid=aid
        )
    )


# ============================================================
# ASSIGNMENT DOWNLOAD
# ============================================================

@app.route(
    "/assignment/<aid>/download"
)
@login_required
def download_assignment(aid):

    assignment = get_assignment(
        aid
    )

    if not assignment:
        abort(404)

    user = current_user()

    if (
        not is_admin()
        and assignment.get(
            "email"
        ) != user.get("email")
        and assignment.get(
            "student_id"
        ) != user.get("id")
    ):

        abort(403)

    try:

        data = storage_download(
            assignment.get(
                "file_path"
            )
        )

        record_document_action(
            aid,
            "assignment_download"
        )

        return send_file(
            io.BytesIO(data),
            as_attachment=True,
            download_name=(
                assignment.get(
                    "file_name"
                )
                or
                "assignment"
            ),
            mimetype=(
                assignment.get(
                    "mime_type"
                )
                or
                "application/octet-stream"
            ),
        )

    except Exception:

        logger.exception(
            "Assignment download failed."
        )

        abort(404)


# ============================================================
# ANSWER PDF DOWNLOAD
# ============================================================

@app.route(
    "/assignment/<aid>/answer/download"
)
@login_required
def download_answer(aid):

    assignment = get_assignment(
        aid
    )

    if not assignment:
        abort(404)

    user = current_user()

    if (
        not is_admin()
        and assignment.get(
            "email"
        ) != user.get("email")
        and assignment.get(
            "student_id"
        ) != user.get("id")
    ):

        abort(403)

    answer = get_answer_for_assignment(
        aid
    )

    if (
        not answer
        or not answer.get(
            "answer_file_path"
        )
    ):

        abort(404)

    try:

        data = storage_download(
            answer.get(
                "answer_file_path"
            )
        )

        record_document_action(
            aid,
            "answer_download"
        )

        return send_file(
            io.BytesIO(data),
            as_attachment=True,
            download_name=(
                answer.get(
                    "answer_file_name"
                )
                or
                "answer.pdf"
            ),
            mimetype="application/pdf",
        )

    except Exception:

        logger.exception(
            "Answer download failed."
        )

        abort(404)


# ============================================================
# ADMIN DASHBOARD
# ============================================================

@app.route("/admin")
@admin_required
def admin_dashboard():

    try:

        assignments = db_select(
            "assignments",
            {
                "select": "id",
            },
        )

    except Exception:

        assignments = []

    try:

        documents = db_select(
            "document_library",
            {
                "select": "id",
                "is_active": "eq.true",
            },
        )

    except Exception:

        documents = []

    try:

        logs = db_select(
            "document_access_logs",
            {
                "select": "id",
            },
        )

    except Exception:

        logs = []

    return page(
        f"""

<div class="grid">

<div class="card">

<h3>
Assignments
</h3>

<div class="stat">
{len(assignments)}
</div>

</div>


<div class="card">

<h3>
Active Resources
</h3>

<div class="stat">
{len(documents)}
</div>

</div>


<div class="card">

<h3>
Access Records
</h3>

<div class="stat">
{len(logs)}
</div>

</div>

</div>


<div class="card">

<h2>
Administrator Dashboard
</h2>

<div class="actions">

<a class="btn"
href="/admin/assignments">

Manage Assignments

</a>

<a class="btn btn-success"
href="/admin/assignment/new">

Send Assignment

</a>

<a class="btn"
href="/admin/document/upload">

Upload Resource

</a>

<a class="btn btn-dark"
href="/admin/documents">

Manage Resources

</a>

<a class="btn"
href="/admin/logs">

Activity Logs

</a>

</div>

</div>

""",
        "Admin Dashboard"
    )


# ============================================================
# ADMIN ASSIGNMENT LIST
# ============================================================

@app.route(
    "/admin/assignments"
)
@admin_required
def admin_assignments():

    try:

        assignments = db_select(
            "assignments",
            {
                "select": "*",
                "order":
                    "created_at.desc",
            },
        )

    except Exception:

        assignments = []

    rows = ""

    for assignment in assignments:

        rows += f"""

<tr>

<td>
{safe_text(
    assignment.get("title")
)}
</td>

<td>
{safe_text(
    assignment.get("student_name")
)}
</td>

<td>
{safe_text(
    assignment.get("email")
)}
</td>

<td>
<span class="badge">

{safe_text(
    assignment.get("status")
)}

</span>

</td>

<td>

<a class="btn"
href="/admin/assignment/"
f"{assignment['id']}">

Open

</a>

</td>

</tr>

"""

    return page(
        f"""

<div class="card">

<h2>
Assignment Management
</h2>

<a class="btn btn-success"
href="/admin/assignment/new">

Send Assignment To Student

</a>

</div>


<div class="card">

<table>

<tr>

<th>
Title
</th>

<th>
Student
</th>

<th>
Email
</th>

<th>
Status
</th>

<th>
Action
</th>

</tr>

{rows or
"<tr><td colspan='5'>No assignments.</td></tr>"}

</table>

</div>

""",
        "Assignments"
    )


# ============================================================
# ADMIN SEND ASSIGNMENT
# ============================================================

@app.route(
    "/admin/assignment/new",
    methods=["GET", "POST"]
)
@admin_required
def admin_new_assignment():

    try:

        users = auth_users()

        students = [
            user
            for user in users
            if (
                user.get("email")
                or ""
            ).lower()
            != ADMIN_EMAIL
        ]

    except Exception:

        logger.exception(
            "Could not load students."
        )

        students = []

        flash(
            "Could not load registered students."
        )

    if request.method == "POST":

        if not csrf_check():
            abort(400)

        student_id = safe_text(
            request.form.get(
                "student_id"
            ),
            100
        )

        title = safe_text(
            request.form.get(
                "title"
            ),
            255
        )

        subject = safe_text(
            request.form.get(
                "subject"
            ),
            255
        )

        course = safe_text(
            request.form.get(
                "course"
            ),
            255
        )

        level = safe_text(
            request.form.get(
                "class_level"
            ),
            255
        )

        question = safe_text(
            request.form.get(
                "question"
            ),
            15000
        )

        comment = safe_text(
            request.form.get(
                "admin_comment"
            ),
            5000
        )

        file = request.files.get(
            "file"
        )

        target = next(
            (
                user
                for user in students
                if user.get("id")
                == student_id
            ),
            None
        )

        if not target:

            flash(
                "Select a valid student."
            )

            return redirect(
                url_for(
                    "admin_new_assignment"
                )
            )

        if not title:

            flash(
                "Assignment title is required."
            )

            return redirect(
                url_for(
                    "admin_new_assignment"
                )
            )

        try:

            assignment_id = str(
                uuid.uuid4()
            )

            filename = None
            path = None
            file_size = 0
            mime = (
                "application/octet-stream"
            )

            if (
                file
                and file.filename
            ):

                if not allowed_file(
                    file.filename
                ):

                    flash(
                        "Unsupported assignment file."
                    )

                    return redirect(
                        url_for(
                            "admin_new_assignment"
                        )
                    )

                data = file.read()

                filename = secure_filename(
                    file.filename
                )

                path = (
                    f"assignments/"
                    f"{assignment_id}/"
                    f"{filename}"
                )

                mime = (
                    file.content_type
                    or
                    "application/octet-stream"
                )

                file_size = len(data)

                storage_upload(
                    data,
                    path,
                    mime
                )

            metadata = (
                target.get(
                    "user_metadata"
                )
                or {}
            )

            student_name = (
                metadata.get("name")
                or target.get("email")
                or "Student"
            )

            db_insert(
                "assignments",
                {
                    "id": assignment_id,
                    "student_id": student_id,
                    "title": title,
                    "description": comment,
                    "subject": subject,
                    "course": course,
                    "class_level": level,
                    "file_name": filename,
                    "file_path": path,
                    "file_size": file_size,
                    "mime_type": mime,
                    "status": "assigned",
                    "admin_comment": comment,
                    "email": target.get(
                        "email"
                    ),
                    "question": question,
                    "student_name": student_name,
                    "created_at": now_iso(),
                    "updated_at": now_iso(),
                },
            )

            flash(
                "Assignment sent directly to the student."
            )

            return redirect(
                url_for(
                    "admin_assignments"
                )
            )

        except Exception as error:

            logger.exception(error)

            flash(
                "Could not send assignment."
            )

    options = ""

    for student in students:

        metadata = (
            student.get(
                "user_metadata"
            )
            or {}
        )

        name = (
            metadata.get("name")
            or student.get("email")
        )

        options += f"""

<option value="{safe_text(student.get('id'))}">

{safe_text(name)}
—
{safe_text(student.get('email'))}

</option>

"""

    return page(
        f"""

<div class="card">

<h2>
Send Assignment Directly To Student
</h2>

<form
method="post"
enctype="multipart/form-data">

<input
type="hidden"
name="csrf_token"
value="{{{{ csrf_token }}}}"
>

<label>
Student
</label>

<select
name="student_id"
required>

<option value="">
Select Student
</option>

{options}

</select>

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
>

<label>
Course
</label>

<input
name="course"
>

<label>
Class Level
</label>

<input
name="class_level"
>

<label>
Question / Instructions
</label>

<textarea
name="question">
</textarea>

<label>
Administrator Comment
</label>

<textarea
name="admin_comment">
</textarea>

<label>
PDF / Word File
</label>

<input
type="file"
name="file"
>

<button>
Send Assignment
</button>

</form>

</div>

""",
        "Send Assignment"
    )


# ============================================================
# ADMIN ASSIGNMENT DETAILS
# ============================================================

@app.route(
    "/admin/assignment/<aid>"
)
@admin_required
def admin_assignment(aid):

    assignment = get_assignment(
        aid
    )

    if not assignment:
        abort(404)

    answer = get_answer_for_assignment(
        aid
    )

    existing_answer = ""

    if answer:

        existing_answer = safe_text(
            answer.get(
                "answer_text"
            )
        )

    statuses = [
        "assigned",
        "submitted",
        "received",
        "reviewing",
        "answered",
        "completed",
        "rejected",
    ]

    status_options = ""

    for status in statuses:

        selected = (
            "selected"
            if status
            == assignment.get(
                "status"
            )
            else ""
        )

        status_options += (
            f"<option {selected}>"
            f"{status}"
            f"</option>"
        )

    try:

        responses = db_select(
            "assignment_responses",
            {
                "assignment_id":
                    f"eq.{aid}",
                "select": "*",
                "order":
                    "created_at.desc",
            },
        )

    except Exception:

        responses = []

    response_html = ""

    for response in responses:

        response_html += f"""

<div class="file-box">

<div class="answer">

{safe_text(
    response.get(
        "response_text"
    )
)}

</div>

<div class="small">

{safe_text(
    response.get(
        "created_at"
    )
)}

</div>

</div>

"""

    return page(
        f"""

<div class="card">

<h2>
{safe_text(
    assignment.get(
        "title"
    )
)}
</h2>

<p>

<b>
Student:
</b>

{safe_text(
    assignment.get(
        "student_name"
    )
)}

</p>

<p>

<b>
Email:
</b>

{safe_text(
    assignment.get(
        "email"
    )
)}

</p>

<p>

<b>
Status:
</b>

<span class="badge">

{safe_text(
    assignment.get(
        "status"
    )
)}

</span>

</p>

<a class="btn"
href="/assignment/{aid}/download">

Download Student Assignment

</a>

<h3>
Question
</h3>

<div class="answer">

{safe_text(
    assignment.get(
        "question"
    )
    or
    assignment.get(
        "description"
    )
)}

</div>

</div>


<div class="card">

<h3>
Status & Comment
</h3>

<form
method="post"
action="/admin/assignment/{aid}/update">

<input
type="hidden"
name="csrf_token"
value="{{{{ csrf_token }}}}"
>

<label>
Status
</label>

<select name="status">

{status_options}

</select>

<label>
Administrator Comment
</label>

<textarea
name="admin_comment">

{safe_text(
    assignment.get(
        "admin_comment"
    )
)}

</textarea>

<button>
Save Status & Comment
</button>

</form>

</div>


<div class="card">

<h3>
Write Answer
</h3>

<form
method="post"
action="/admin/assignment/{aid}/answer">

<input
type="hidden"
name="csrf_token"
value="{{{{ csrf_token }}}}"
>

<textarea
name="answer"
style="min-height:350px"
required>

{existing_answer}

</textarea>

<button>
Save Answer & Generate PDF
</button>

</form>

<p class="small">

The KOJA brain screen symbol is NOT
included in the generated PDF.

</p>

</div>


<div class="card">

<h3>
Student Comments / Responses
</h3>

{response_html or
"<p>No responses yet.</p>"}

</div>

""",
        "Manage Assignment"
    )


# ============================================================
# ADMIN UPDATE ASSIGNMENT
# ============================================================

@app.route(
    "/admin/assignment/<aid>/update",
    methods=["POST"]
)
@admin_required
def update_assignment(aid):

    if not csrf_check():
        abort(400)

    assignment = get_assignment(
        aid
    )

    if not assignment:
        abort(404)

    status = safe_text(
        request.form.get(
            "status"
        ),
        50
    )

    comment = safe_text(
        request.form.get(
            "admin_comment"
        ),
        5000
    )

    allowed_statuses = {
        "assigned",
        "submitted",
        "received",
        "reviewing",
        "answered",
        "completed",
        "rejected",
    }

    if status not in allowed_statuses:

        flash(
            "Invalid assignment status."
        )

        return redirect(
            url_for(
                "admin_assignment",
                aid=aid
            )
        )

    try:

        db_update(
            "assignments",
            {
                "id":
                    f"eq.{aid}"
            },
            {
                "status": status,
                "admin_comment": comment,
                "reviewed_by":
                    current_user_id(),
                "updated_at":
                    now_iso(),
            },
        )

        flash(
            "Assignment updated."
        )

    except Exception as error:

        logger.exception(error)

        flash(
            "Could not update assignment."
        )

    return redirect(
        url_for(
            "admin_assignment",
            aid=aid
        )
    )


# ============================================================
# ADMIN SAVE ANSWER
# ============================================================

@app.route(
    "/admin/assignment/<aid>/answer",
    methods=["POST"]
)
@admin_required
def save_answer(aid):

    if not csrf_check():
        abort(400)

    assignment = get_assignment(
        aid
    )

    if not assignment:
        abort(404)

    answer_text = safe_text(
        request.form.get(
            "answer"
        ),
        50000
    )

    if not answer_text:

        flash(
            "Answer cannot be empty."
        )

        return redirect(
            url_for(
                "admin_assignment",
                aid=aid
            )
        )

    try:

        pdf = build_pdf(
            assignment.get(
                "title"
            )
            or
            "Assignment",

            assignment.get(
                "subject"
            )
            or
            "",

            assignment.get(
                "student_name"
            )
            or
            "",

            assignment.get(
                "question"
            )
            or
            assignment.get(
                "description"
            )
            or
            "",

            answer_text,
        )

        base_name = secure_filename(
            assignment.get(
                "title"
            )
            or
            "answer"
        )

        pdf_name = (
            f"{base_name}"
            "_answered.pdf"
        )

        path = (
            f"answer-pdfs/"
            f"{aid}/"
            f"{uuid.uuid4()}_"
            f"{pdf_name}"
        )

        storage_upload(
            pdf,
            path,
            "application/pdf"
        )

        old = get_answer_for_assignment(
            aid
        )

        answer_data = {
            "assignment_id": aid,
            "student_id":
                assignment.get(
                    "student_id"
                ),
            "answer_text":
                answer_text,
            "answer_file_name":
                pdf_name,
            "answer_file_path":
                path,
            "generated_by":
                "Administrator",
            "status":
                "published",
            "updated_at":
                now_iso(),
        }

        if old:

            db_update(
                "assignment_answers",
                {
                    "id":
                        f"eq.{old['id']}"
                },
                answer_data,
            )

        else:

            answer_data[
                "id"
            ] = str(
                uuid.uuid4()
            )

            db_insert(
                "assignment_answers",
                answer_data
            )

        db_update(
            "assignments",
            {
                "id":
                    f"eq.{aid}"
            },
            {
                "answer_file_name":
                    pdf_name,

                "answer_file_path":
                    path,

                "answered_at":
                    now_iso(),

                "answered_by":
                    current_user_id(),

                "status":
                    "answered",

                "updated_at":
                    now_iso(),
            },
        )

        flash(
            "Answer saved and clean PDF generated."
        )

    except Exception as error:

        logger.exception(error)

        flash(
            "Could not save answer."
        )

    return redirect(
        url_for(
            "admin_assignment",
            aid=aid
        )
    )


# ============================================================
# DOCUMENT LIBRARY
# ============================================================

@app.route("/documents")
@login_required
def documents():

    search = safe_text(
        request.args.get(
            "q"
        ),
        255
    )

    document_type = safe_text(
        request.args.get(
            "type"
        ),
        100
    )

    try:

        params = {
            "select": "*",
            "order":
                "created_at.desc",
        }

        if search:

            term = (
                search
                .replace(",", " ")
                .replace("(", " ")
                .replace(")", " ")
            )

            params["or"] = (
                f"title.ilike.*{term}*,"
                f"description.ilike.*{term}*,"
                f"subject.ilike.*{term}*,"
                f"course.ilike.*{term}*"
            )

        if document_type:

            params[
                "document_type"
            ] = (
                f"eq.{document_type}"
            )

        params[
            "is_active"
        ] = "eq.true"

        resources = db_select(
            "document_library",
            params
        )

    except Exception:

        logger.exception(
            "Could not load document library."
        )

        resources = []

    rows = ""

    for resource in resources:

        rows += f"""

<tr>

<td>
{safe_text(
    resource.get("title")
)}
</td>

<td>
{safe_text(
    resource.get(
        "document_type"
    )
)}
</td>

<td>
{safe_text(
    resource.get(
        "subject"
    )
)}
</td>

<td>
{safe_text(
    resource.get(
        "course"
    )
)}
</td>

<td>

<span class="badge">

Views:
{int(
    resource.get(
        "view_count"
    )
    or 0
)}

</span>

<span class="badge">

Downloads:
{int(
    resource.get(
        "download_count"
    )
    or 0
)}

</span>

</td>

<td>

<a class="btn"
href="/document/"
f"{resource.get('id')}/view">

View

</a>

</td>

</tr>

"""

    return page(
        f"""

<div class="card">

<h2>
KOJA Learning Library
</h2>

<p class="small">

Past Papers • Notes • Books
• Academic Resources

</p>

<form method="get">

<input
name="q"
value="{safe_text(search)}"
placeholder="Search resources..."
>

<select name="type">

<option value="">
All Types
</option>

<option value="past_paper">
Past Papers
</option>

<option value="notes">
Notes
</option>

<option value="book">
Books
</option>

<option value="academic">
Academic
</option>

</select>

<button>
Search
</button>

</form>

</div>


<div class="card">

<table>

<tr>

<th>
Title
</th>

<th>
Type
</th>

<th>
Subject
</th>

<th>
Course
</th>

<th>
Statistics
</th>

<th>
Action
</th>

</tr>

{rows or
"<tr><td colspan='6'>No resources found.</td></tr>"}

</table>

</div>

""",
        "Learning Library"
    )


# ============================================================
# DOCUMENT VIEW
# ============================================================

@app.route(
    "/document/<did>/view"
)
@login_required
def document_view(did):

    document = get_document(
        did
    )

    if (
        not document
        or document.get(
            "is_active"
        ) is False
    ):

        abort(404)

    # Public resources are visible to logged users.
    # Non-public resources remain available to
    # authenticated users through this protected route.

    try:

        views = int(
            document.get(
                "view_count"
            )
            or 0
        ) + 1

        db_update(
            "document_library",
            {
                "id":
                    f"eq.{did}"
            },
            {
                "view_count":
                    views,
                "updated_at":
                    now_iso(),
            },
        )

        access_log(
            did,
            "view"
        )

        record_document_action(
            did,
            "view"
        )

    except Exception:

        logger.exception(
            "Could not update document view."
        )

    return page(
        f"""

<div class="card">

<h2>
{safe_text(
    document.get(
        "title"
    )
)}
</h2>

<p>

<b>
Type:
</b>

{safe_text(
    document.get(
        "document_type"
    )
)}

</p>

<p>

<b>
Subject:
</b>

{safe_text(
    document.get(
        "subject"
    )
)}

</p>

<p>

<b>
Course:
</b>

{safe_text(
    document.get(
        "course"
    )
)}

</p>

<p>

<b>
Description:
</b>

{safe_text(
    document.get(
        "description"
    )
)}

</p>

<div class="file-box">

<b>
File:
</b>

{safe_text(
    document.get(
        "file_name"
    )
)}

</div>

<br>

<div class="actions">

<a class="btn"
href="/document/{did}/download">

Download

</a>

<a class="btn btn-dark"
href="/documents">

Back To Library

</a>

</div>

</div>

""",
        "View Resource"
    )


# ============================================================
# DOCUMENT DOWNLOAD
# ============================================================

@app.route(
    "/document/<did>/download"
)
@login_required
def document_download(did):

    document = get_document(
        did
    )

    if (
        not document
        or document.get(
            "is_active"
        ) is False
    ):

        abort(404)

    try:

        data = storage_download(
            document.get(
                "file_path"
            )
        )

        downloads = int(
            document.get(
                "download_count"
            )
            or 0
        ) + 1

        views = int(
            document.get(
                "view_count"
            )
            or 0
        )

        db_update(
            "document_library",
            {
                "id":
                    f"eq.{did}"
            },
            {
                "download_count":
                    downloads,

                "view_count":
                    views,

                "updated_at":
                    now_iso(),
            },
        )

        access_log(
            did,
            "download"
        )

        record_document_action(
            did,
            "download"
        )

        return send_file(
            io.BytesIO(data),
            as_attachment=True,
            download_name=(
                document.get(
                    "file_name"
                )
                or
                "document"
            ),
            mimetype=(
                document.get(
                    "mime_type"
                )
                or
                "application/octet-stream"
            ),
        )

    except Exception:

        logger.exception(
            "Document download failed."
        )

        abort(404)


# ============================================================
# ADMIN RESOURCE UPLOAD
# ============================================================

@app.route(
    "/admin/document/upload",
    methods=["GET", "POST"]
)
@admin_required
def admin_document_upload():

    if request.method == "POST":

        if not csrf_check():
            abort(400)

        title = safe_text(
            request.form.get(
                "title"
            ),
            255
        )

        description = safe_text(
            request.form.get(
                "description"
            ),
            5000
        )

        document_type = safe_text(
            request.form.get(
                "document_type"
            ),
            100
        ) or "academic"

        subject = safe_text(
            request.form.get(
                "subject"
            ),
            255
        )

        course = safe_text(
            request.form.get(
                "course"
            ),
            255
        )

        class_level = safe_text(
            request.form.get(
                "class_level"
            ),
            255
        )

        is_public = (
            request.form.get(
                "is_public"
            )
            == "on"
        )

        file = request.files.get(
            "file"
        )

        if (
            not title
            or not file
            or not file.filename
            or not allowed_file(
                file.filename
            )
        ):

            flash(
                "Title and supported file are required."
            )

            return redirect(
                url_for(
                    "admin_document_upload"
                )
            )

        try:

            document_id = str(
                uuid.uuid4()
            )

            filename = secure_filename(
                file.filename
            )

            data = file.read()

            mime = (
                file.content_type
                or
                "application/octet-stream"
            )

            path = (
                f"library/"
                f"{document_id}/"
                f"{filename}"
            )

            storage_upload(
                data,
                path,
                mime
            )

            user = current_user()

            db_insert(
                "document_library",
                {
                    "id": document_id,

                    "title": title,

                    "description":
                        description,

                    "document_type":
                        document_type,

                    "subject":
                        subject,

                    "course":
                        course,

                    "class_level":
                        class_level,

                    "file_name":
                        filename,

                    "file_path":
                        path,

                    "file_url":
                        None,

                    "file_size":
                        len(data),

                    "mime_type":
                        mime,

                    "uploaded_by":
                        current_user_id(),

                    "uploader_name":
                        user.get(
                            "student_name"
                        ),

                    "uploader_email":
                        user.get(
                            "email"
                        ),

                    "uploader_role":
                        "admin",

                    "is_public":
                        is_public,

                    "is_active":
                        True,

                    "download_count":
                        0,

                    "view_count":
                        0,

                    "created_at":
                        now_iso(),

                    "updated_at":
                        now_iso(),
                },
            )

            flash(
                "Resource uploaded successfully."
            )

            return redirect(
                url_for(
                    "admin_documents"
                )
            )

        except Exception as error:

            logger.exception(error)

            flash(
                "Resource upload failed."
            )

    return page(
        """

<div class="card">

<h2>
Upload Learning Resource
</h2>

<p class="small">

Past Papers • Notes • Books
• Academic Documents

</p>

<form
method="post"
enctype="multipart/form-data">

<input
type="hidden"
name="csrf_token"
value="{{ csrf_token }}"
>

<label>
Title
</label>

<input
name="title"
required
>

<label>
Description
</label>

<textarea
name="description">
</textarea>

<label>
Resource Type
</label>

<select
name="document_type">

<option value="past_paper">
Past Paper
</option>

<option value="notes">
Notes
</option>

<option value="book">
Book
</option>

<option value="academic">
Academic
</option>

<option value="other">
Other
</option>

</select>

<label>
Subject
</label>

<input
name="subject"
>

<label>
Course
</label>

<input
name="course"
>

<label>
Class Level
</label>

<input
name="class_level"
>

<label>
File
</label>

<input
type="file"
name="file"
required
>

<label>

<input
type="checkbox"
name="is_public"
>

Public Resource

</label>

<br><br>

<button>
Upload Resource
</button>

</form>

</div>

""",
        "Upload Resource"
    )


# ============================================================
# STUDENT RESOURCE UPLOAD
# ============================================================

@app.route(
    "/student/document/upload",
    methods=["GET", "POST"]
)
@student_required
def student_document_upload():

    if request.method == "POST":

        if not csrf_check():
            abort(400)

        title = safe_text(
            request.form.get(
                "title"
            ),
            255
        )

        description = safe_text(
            request.form.get(
                "description"
            ),
            5000
        )

        document_type = safe_text(
            request.form.get(
                "document_type"
            ),
            100
        ) or "academic"

        subject = safe_text(
            request.form.get(
                "subject"
            ),
            255
        )

        course = safe_text(
            request.form.get(
                "course"
            ),
            255
        )

        class_level = safe_text(
            request.form.get(
                "class_level"
            ),
            255
        )

        file = request.files.get(
            "file"
        )

        if (
            not title
            or not file
            or not file.filename
            or not allowed_file(
                file.filename
            )
        ):

            flash(
                "Title and supported file are required."
            )

            return redirect(
                url_for(
                    "student_document_upload"
                )
            )

        try:

            document_id = str(
                uuid.uuid4()
            )

            filename = secure_filename(
                file.filename
            )

            data = file.read()

            mime = (
                file.content_type
                or
                "application/octet-stream"
            )

            path = (
                f"student-resources/"
                f"{document_id}/"
                f"{filename}"
            )

            storage_upload(
                data,
                path,
                mime
            )

            user = current_user()

            db_insert(
                "document_library",
                {
                    "id": document_id,

                    "title": title,

                    "description":
                        description,

                    "document_type":
                        document_type,

                    "subject":
                        subject,

                    "course":
                        course,

                    "class_level":
                        class_level,

                    "file_name":
                        filename,

                    "file_path":
                        path,

                    "file_url":
                        None,

                    "file_size":
                        len(data),

                    "mime_type":
                        mime,

                    "uploaded_by":
                        current_user_id(),

                    "uploader_name":
                        user.get(
                            "student_name"
                        ),

                    "uploader_email":
                        user.get(
                            "email"
                        ),

                    "uploader_role":
                        "student",

                    "is_public":
                        False,

                    "is_active":
                        True,

                    "download_count":
                        0,

                    "view_count":
                        0,

                    "created_at":
                        now_iso(),

                    "updated_at":
                        now_iso(),
                },
            )

            flash(
                "Your resource has been uploaded."
            )

            return redirect(
                url_for(
                    "documents"
                )
            )

        except Exception as error:

            logger.exception(error)

            flash(
                "Resource upload failed."
            )

    return page(
        """

<div class="card">

<h2>
Upload Academic Resource
</h2>

<p class="small">

Students can contribute notes,
past papers and other learning materials.

</p>

<form
method="post"
enctype="multipart/form-data">

<input
type="hidden"
name="csrf_token"
value="{{ csrf_token }}"
>

<label>
Title
</label>

<input
name="title"
required
>

<label>
Description
</label>

<textarea
name="description">
</textarea>

<label>
Type
</label>

<select
name="document_type">

<option value="past_paper">
Past Paper
</option>

<option value="notes">
Notes
</option>

<option value="book">
Book
</option>

<option value="academic">
Academic
</option>

<option value="other">
Other
</option>

</select>

<label>
Subject
</label>

<input
name="subject"
>

<label>
Course
</label>

<input
name="course"
>

<label>
Class Level
</label>

<input
name="class_level"
>

<label>
File
</label>

<input
type="file"
name="file"
required
>

<button>
Upload Resource
</button>

</form>

</div>

""",
        "Upload Resource"
    )


# ============================================================
# ADMIN RESOURCE MANAGEMENT
# ============================================================

@app.route(
    "/admin/documents"
)
@admin_required
def admin_documents():

    try:

        documents = db_select(
            "document_library",
            {
                "select": "*",
                "order":
                    "created_at.desc",
            },
        )

    except Exception:

        documents = []

    rows = ""

    for document in documents:

        active = (
            document.get(
                "is_active"
            )
            is not False
        )

        action_text = (
            "Hide"
            if active
            else
            "Show"
        )

        rows += f"""

<tr>

<td>
{safe_text(
    document.get(
        "title"
    )
)}
</td>

<td>
{safe_text(
    document.get(
        "document_type"
    )
)}
</td>

<td>
{safe_text(
    document.get(
        "uploader_role"
    )
)}
</td>

<td>

<span class="badge">

{"Active" if active else "Hidden"}

</span>

</td>

<td>

{int(
    document.get(
        "view_count"
    )
    or 0
)}

</td>

<td>

{int(
    document.get(
        "download_count"
    )
    or 0
)}

</td>

<td>

<div class="actions">

<a class="btn"
href="/document/"
f"{document.get('id')}/view">

View

</a>

<form
method="post"
action="/admin/document/"
f"{document.get('id')}/toggle"
style="display:inline">

<input
type="hidden"
name="csrf_token"
value="{{{{ csrf_token }}}}"
>

<button
class="btn btn-dark">

{action_text}

</button>

</form>

</div>

</td>

</tr>

"""

    return page(
        f"""

<div class="card">

<h2>
Manage Learning Resources
</h2>

<a class="btn btn-success"
href="/admin/document/upload">

Upload New Resource

</a>

</div>


<div class="card">

<table>

<tr>

<th>
Title
</th>

<th>
Type
</th>

<th>
Uploader
</th>

<th>
Status
</th>

<th>
Views
</th>

<th>
Downloads
</th>

<th>
Action
</th>

</tr>

{rows or
"<tr><td colspan='7'>No resources.</td></tr>"}

</table>

</div>

""",
        "Manage Resources"
    )


# ============================================================
# ADMIN HIDE / SHOW DOCUMENT
# ============================================================

@app.route(
    "/admin/document/<did>/toggle",
    methods=["POST"]
)
@admin_required
def toggle_document(did):

    if not csrf_check():
        abort(400)

    document = get_document(
        did
    )

    if not document:
        abort(404)

    current = (
        document.get(
            "is_active"
        )
        is not False
    )

    try:

        db_update(
            "document_library",
            {
                "id":
                    f"eq.{did}"
            },
            {
                "is_active":
                    not current,

                "updated_at":
                    now_iso(),
            },
        )

        record_document_action(
            did,
            (
                "document_hidden"
                if current
                else
                "document_shown"
            )
        )

        flash(
            "Document status updated."
        )

    except Exception:

        logger.exception(
            "Could not toggle document."
        )

        flash(
            "Could not update document."
        )

    return redirect(
        url_for(
            "admin_documents"
        )
    )


# ============================================================
# ADMIN LOGS
# ============================================================

@app.route(
    "/admin/logs"
)
@admin_required
def admin_logs():

    try:

        access_logs = db_select(
            "document_access_logs",
            {
                "select": "*",
                "order":
                    "created_at.desc",
                "limit": "300",
            },
        )

    except Exception:

        access_logs = []

    rows = ""

    for log in access_logs:

        rows += f"""

<tr>

<td>
{safe_text(
    log.get(
        "action"
    )
)}
</td>

<td>
{safe_text(
    log.get(
        "user_id"
    )
)}
</td>

<td>
{safe_text(
    log.get(
        "document_id"
    )
)}
</td>

<td>
{safe_text(
    log.get(
        "created_at"
    )
)}
</td>

</tr>

"""

    return page(
        f"""

<div class="card">

<h2>
KOJA Activity Logs
</h2>

<p class="small">

This page is available to administrators only.

The first web-open event is recorded once
per login session.

</p>

<table>

<tr>

<th>
Action
</th>

<th>
User
</th>

<th>
Document
</th>

<th>
Time
</th>

</tr>

{rows or
"<tr><td colspan='4'>No access logs.</td></tr>"}

</table>

</div>

""",
        "Admin Logs"
    )


# ============================================================
# HEALTH
# ============================================================

@app.route("/health")
def health():

    missing = []

    if not SUPABASE_URL:
        missing.append(
            "SUPABASE_URL"
        )

    if not SUPABASE_SERVICE_KEY:
        missing.append(
            "SUPABASE_SERVICE_KEY"
        )

    if not ADMIN_EMAIL:
        missing.append(
            "KOJA_ADMIN_EMAIL"
        )

    if not ADMIN_PASSWORD:
        missing.append(
            "KOJA_ADMIN_PASSWORD"
        )

    if missing:

        return jsonify(
            {
                "status": "error",
                "missing": missing,
            }
        ), 500

    try:

        response = sb_request(
            "GET",
            "assignments",
            {
                "select": "id",
                "limit": "1",
            },
            timeout=10,
        )

        if not response.ok:

            return jsonify(
                {
                    "status": "error",
                    "supabase":
                        response.text,
                }
            ), 500

        return jsonify(
            {
                "status": "ok",
                "app": APP_NAME,
                "supabase":
                    "connected",
                "ai": False,
                "version":
                    "KOJA-UPDATED-2026",
            }
        )

    except Exception as error:

        return jsonify(
            {
                "status": "error",
                "message":
                    str(error),
            }
        ), 500


# ============================================================
# ERROR HANDLERS
# ============================================================

@app.errorhandler(413)
def too_large(error):

    return page(
        """

<div class="card">

<h2>
File Too Large
</h2>

<p>
The maximum upload size is 20 MB.
</p>

</div>

""",
        "File Too Large"
    ), 413


@app.errorhandler(404)
def not_found(error):

    return page(
        """

<div class="card">

<h2>
Page Not Found
</h2>

<a class="btn"
href="/">

Home

</a>

</div>

""",
        "Not Found"
    ), 404


@app.errorhandler(403)
def forbidden(error):

    return page(
        """

<div class="card">

<h2>
Access Denied
</h2>

<p>
You do not have permission to access
this resource.
</p>

</div>

""",
        "Access Denied"
    ), 403


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            "5000"
        )
    )

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False,
    )

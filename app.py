import os
import uuid
import logging
from datetime import datetime, timezone
from functools import wraps
from io import BytesIO

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
    send_file,
)

from werkzeug.utils import secure_filename

load_dotenv()

# ============================================================
# KOJA AFRICA
# ONE FLASK APPLICATION
#
# SERVICES
# 1. Assignments
# 2. Drivers + Delivery + Live GPS
# 3. Professional Services
# ============================================================

app = Flask(__name__)

app.secret_key = os.getenv(
    "FLASK_SECRET_KEY",
    "CHANGE_THIS_SECRET"
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

logger = logging.getLogger("koja")


# ============================================================
# BASIC
# ============================================================

def now_iso():
    return datetime.now(
        timezone.utc
    ).isoformat()


def configuration_ok():
    return bool(
        SUPABASE_URL and
        SUPABASE_SERVICE_KEY
    )


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


def allowed_file(filename):
    if not filename or "." not in filename:
        return False

    extension = filename.rsplit(
        ".",
        1
    )[1].lower()

    return extension in ALLOWED_EXTENSIONS


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

    except Exception as exc:
        logger.exception(
            "Supabase GET error"
        )
        return None, str(exc)


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

    except Exception as exc:
        logger.exception(
            "Supabase INSERT error"
        )
        return None, str(exc)


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

    except Exception as exc:
        logger.exception(
            "Supabase UPDATE error"
        )
        return None, str(exc)


# ============================================================
# SUPABASE AUTH
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
        return None, str(exc)


def auth_login(email, password):
    try:
        response = requests.post(
            f"{SUPABASE_URL}/auth/v1/token?grant_type=password",
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
        or "application/octet-stream"
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
            "path":
                object_name,
            "filename":
                filename,
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
# SESSION
# ============================================================

def current_user():
    return session.get("user")


def logged_in():
    return bool(
        current_user()
    )


def is_admin():
    account = current_user()

    if not account:
        return False

    return (
        account.get("email", "").lower()
        == ADMIN_EMAIL
        and
        ADMIN_EMAIL != ""
    )


def login_required(function):
    @wraps(function)
    def wrapper(*args, **kwargs):

        if not logged_in():
            flash(
                "Please login first."
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
# HTML
# ============================================================

PAGE = """
<!DOCTYPE html>
<html>

<head>

<meta charset="UTF-8">

<meta name="viewport"
      content="width=device-width,
               initial-scale=1">

<title>
{{ title }} - KOJA AFRICA
</title>

<link rel="stylesheet"
      href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">

<style>

*{
    box-sizing:border-box;
}

body{
    margin:0;
    background:#f3f6fa;
    color:#172033;
    font-family:Arial,sans-serif;
}

nav{
    background:#111827;
    color:white;
    padding:15px;
}

.brand{
    font-size:23px;
    font-weight:bold;
}

nav a{
    color:white;
    text-decoration:none;
    margin:7px 10px 0 0;
    display:inline-block;
}

.container{
    max-width:1150px;
    margin:auto;
    padding:20px;
}

.hero{
    background:
    linear-gradient(
        135deg,
        #0f766e,
        #2563eb
    );
    color:white;
    padding:30px;
    border-radius:18px;
    margin-bottom:20px;
}

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
    padding:20px;
    margin-bottom:18px;
    border-radius:15px;
    box-shadow:
    0 3px 12px
    rgba(0,0,0,.07);
}

input,
textarea,
select{
    width:100%;
    padding:12px;
    margin:6px 0 14px;
    border:1px solid #d1d5db;
    border-radius:9px;
    font-size:15px;
}

textarea{
    min-height:130px;
}

button,
.btn{
    border:0;
    border-radius:9px;
    padding:11px 17px;
    background:#2563eb;
    color:white;
    text-decoration:none;
    cursor:pointer;
    display:inline-block;
}

.green{
    background:#059669;
}

.orange{
    background:#d97706;
}

.red{
    background:#dc2626;
}

.dark{
    background:#111827;
}

.status{
    display:inline-block;
    background:#e5e7eb;
    padding:5px 10px;
    border-radius:20px;
    font-size:13px;
}

.online{
    color:#047857;
    font-weight:bold;
}

.location{
    color:#1d4ed8;
    font-weight:bold;
}

.flash{
    background:#fff7ed;
    padding:12px;
    border-radius:8px;
    margin-bottom:10px;
}

.small{
    color:#6b7280;
    font-size:13px;
}

#map{
    height:420px;
    width:100%;
    border-radius:15px;
    margin-top:15px;
}

.gps-box{
    background:#ecfdf5;
    padding:15px;
    border-radius:12px;
    margin-bottom:15px;
}

.gps-error{
    background:#fef2f2;
    padding:15px;
    border-radius:12px;
}

footer{
    text-align:center;
    padding:30px;
    color:#6b7280;
}

</style>

</head>

<body>

<nav>

<span class="brand">
KOJA AFRICA
</span>

<br>

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
My Deliveries
</a>

<a href="/bookings">
Bookings
</a>

<a href="/professionals">
Professionals
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

</nav>

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

<footer>

KOJA AFRICA<br>

Assignments • Drivers & Delivery •
Professional Services

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

<h1>KOJA AFRICA</h1>

<p>
Knowledge • Questions • Answers
</p>

<p>
Academic assistance, real-time
drivers and delivery, and
professional services.
</p>

<a class="btn"
   href="/register">
Create Account
</a>

<a class="btn dark"
   href="/login">
Login
</a>

</div>

<div class="grid">

<div class="card">

<h2>
📚 Assignments
</h2>

<p>
Submit academic questions,
upload documents and receive
answers from the administrator.
</p>

<a class="btn"
   href="/assignments">
Assignments
</a>

</div>


<div class="card">

<h2>
🚗 Drivers & Delivery
</h2>

<p>
Request a driver and follow the
driver's real GPS position on a
live map.
</p>

<a class="btn green"
   href="/drivers">
Find Driver
</a>

</div>


<div class="card">

<h2>
👨‍⚕️ Professional Services
</h2>

<p>
Find approved professionals and
request appointments.
</p>

<a class="btn orange"
   href="/professionals">
Professionals
</a>

</div>

</div>

"""

    return render_page(
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

<form method="POST">

<label>
Email
</label>

<input
type="email"
name="email"
required>

<label>
Password
</label>

<input
type="password"
name="password"
minlength="6"
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
                "Login failed. Check your "
                "email and password."
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
required>

<label>
Password
</label>

<input
type="password"
name="password"
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

    account = current_user()

    content = f"""

<div class="hero">

<h1>
Dashboard
</h1>

<p>
{account.get("email")}
</p>

</div>

<div class="grid">

<div class="card">

<h2>
📚 Assignments
</h2>

<a class="btn"
href="/assignments/new">
New Assignment
</a>

<br><br>

<a class="btn dark"
href="/assignments">
My Assignments
</a>

</div>


<div class="card">

<h2>
🚗 Driver
</h2>

<a class="btn green"
href="/drivers/register">
Register as Driver
</a>

<br><br>

<a class="btn dark"
href="/driver">
Driver GPS
</a>

</div>


<div class="card">

<h2>
📦 Delivery
</h2>

<a class="btn green"
href="/drivers">
Find Driver
</a>

<br><br>

<a class="btn dark"
href="/deliveries">
Track Deliveries
</a>

</div>


<div class="card">

<h2>
👨‍⚕️ Professional
</h2>

<a class="btn orange"
href="/professionals/register">
Register
</a>

<br><br>

<a class="btn dark"
href="/professionals">
Find Professional
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

        flash(
            "Unable to load assignments."
        )

        rows = []

    cards = ""

    for assignment in rows or []:

        cards += f"""

<div class="card">

<h3>
{assignment.get("title")
 or "Assignment"}
</h3>

<p>
<b>Subject:</b>
{assignment.get("subject")
 or ""}
</p>

<p>
<b>Status:</b>

<span class="status">
{assignment.get("status")
 or "pending"}
</span>

</p>

<a class="btn"
href="/assignments/
{assignment.get("id")}">

View Assignment

</a>

"""

        note = (
            assignment.get(
                "admin_note"
            )
            or ""
        )

        if "ANSWER_FILE|" in note:

            cards += f"""

<a class="btn green"
href="/assignment-file/
{assignment.get("id")}/answer">

Download Answer

</a>

"""

        cards += "</div>"

    content = f"""

<div class="hero">

<h1>
My Assignments
</h1>

<a class="btn"
href="/assignments/new">
New Assignment
</a>

</div>

{cards or
'<div class="card">No assignments yet.</div>'}

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

<div class="card">

<h2>
New Assignment
</h2>

<form method="POST"
enctype="multipart/form-data">

<label>
Title
</label>

<input
name="title"
required>

<label>
Subject
</label>

<input
name="subject"
required>

<label>
Question
</label>

<textarea
name="description"
required></textarea>

<label>
Question PDF / Word / Image
</label>

<input
type="file"
name="question_file"
accept=".pdf,.doc,.docx,.jpg,.jpeg,.png,.webp">

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


@app.route(
    "/assignments/<assignment_id>"
)
@login_required
def assignment_detail(
    assignment_id
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

        flash(
            "Assignment not found."
        )

        return redirect(
            url_for("assignments")
        )

    a = rows[0]

    content = f"""

<div class="card">

<h2>
{a.get("title") or ""}
</h2>

<p>
<b>Subject:</b>
{a.get("subject") or ""}
</p>

<p>
<b>Status:</b>

<span class="status">
{a.get("status") or "pending"}
</span>

</p>

<hr>

<h3>
Question
</h3>

<p>
{a.get("description") or ""}
</p>

"""

    note = a.get(
        "admin_note"
    ) or ""

    if "QUESTION_FILE|" in note:

        content += f"""

<a class="btn"
href="/assignment-file/
{assignment_id}/question">

Download Question File

</a>

"""

    content += f"""

</div>

<div class="card">

<h2>
Answer
</h2>

<p>
{a.get("answer_text")
 or "Your answer has not been completed yet."}
</p>

"""

    if "ANSWER_FILE|" in note:

        content += f"""

<a class="btn green"
href="/assignment-file/
{assignment_id}/answer">

Download Answer File

</a>

"""

    content += """

</div>

<a class="btn"
href="/assignments">
Back
</a>

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
{a.get("student_id")}
</p>

<p>
Subject:
{a.get("subject") or ""}
</p>

<p>
Status:
<span class="status">
{a.get("status") or ""}
</span>
</p>

<a class="btn"
href="/admin/assignments/
{a.get("id")}">

Process

</a>

</div>

"""

    content = f"""

<div class="hero">

<h1>
KOJA AFRICA ADMIN
</h1>

<p>
Manage the three KOJA services.
</p>

<a class="btn green"
href="/admin/drivers">
Drivers
</a>

<a class="btn orange"
href="/admin/deliveries">
Deliveries
</a>

<a class="btn dark"
href="/admin/professionals">
Professionals
</a>

<a class="btn"
href="/admin/bookings">
Bookings
</a>

</div>

{cards or
'<div class="card">No assignments.</div>'}

"""

    return render_page(
        content,
        "Admin"
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
            url_for("admin")
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
                "Could not update assignment: "
                + str(update_error)
            )

        else:

            flash(
                "Assignment updated."
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
<b>Student:</b>
{assignment.get("student_id")}
</p>

<p>
<b>Subject:</b>
{assignment.get("subject") or ""}
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

<textarea
name="admin_note">{assignment.get("admin_note") or ""}</textarea>


<label>
Written Answer
</label>

<textarea
name="answer_text">{assignment.get("answer_text") or ""}</textarea>


<label>
Answer PDF / Word
</label>

<input
type="file"
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
# ASSIGNMENT FILE
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
        else "QUESTION_FILE|"
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

    content, error = storage_download(
        path
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
                location_name,

            "last_location_update":
                None
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
            "Driver registration submitted "
            "for admin approval."
        )

        return redirect(
            url_for("drivers")
        )

    content = """

<div class="card">

<h2>
Driver Registration
</h2>

<form method="POST">

<label>
Vehicle Type
</label>

<input
name="vehicle_type"
placeholder="Car, motorcycle, van..."
required>


<label>
Vehicle Number
</label>

<input
name="vehicle_number"
required>


<label>
License Number
</label>

<input
name="license_number"
required>


<label>
Current Location Name
</label>

<input
name="location_name"
placeholder="Example: Kitwe City Square">


<button>
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
# DRIVER LIST
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
            "Could not load drivers."
        )

        rows = []

    cards = ""

    for driver in rows or []:

        cards += f"""

<div class="card">

<h3>
🚗 {driver.get("vehicle_type")
or "Driver"}
</h3>

<p>
Vehicle:
{driver.get("vehicle_number")
or ""}
</p>

<p class="location">
📍 {driver.get("location_name")
or "GPS location available"}
</p>

<p class="online">
● ONLINE
</p>

<p class="small">
Last GPS update:
{driver.get("last_location_update")
or "Not available"}
</p>

<form method="POST"
action="/delivery/request">

<input
type="hidden"
name="driver_id"
value="{driver.get("id")}">

<input
type="hidden"
name="service_type"
value="delivery">


<label>
Pickup
</label>

<input
name="pickup_location"
placeholder="Pickup location"
required>


<label>
Destination
</label>

<input
name="destination_location"
placeholder="Destination"
required>


<label>
Notes
</label>

<textarea
name="notes"
placeholder="Delivery instructions"></textarea>


<button class="green">
Request Driver
</button>

</form>

</div>

"""

    content = f"""

<div class="hero">

<h1>
Available Drivers
</h1>

<p>
Approved drivers currently sharing
their GPS location appear here.
</p>

<a class="btn"
href="/drivers/register">
Register as Driver
</a>

</div>

<div class="grid">

{cards or
'<div class="card">No online drivers available.</div>'}

</div>

"""

    return render_page(
        content,
        "Drivers"
    )


# ============================================================
# DRIVER GPS PAGE
# ============================================================

@app.route("/driver")
@login_required
def driver_page():

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

<h2>
Driver Profile Not Found
</h2>

<p>
Register as a driver first.
</p>

<a class="btn"
href="/drivers/register">
Register Driver
</a>

</div>

"""

        return render_page(
            content,
            "Driver GPS"
        )

    driver = rows[0]

    if driver.get("status") != "approved":

        content = """

<div class="card">

<h2>
Driver Approval Required
</h2>

<p>
Your driver registration is waiting
for administrator approval.
</p>

</div>

"""

        return render_page(
            content,
            "Driver GPS"
        )

    content = f"""

<div class="hero">

<h1>
Driver GPS Tracking
</h1>

<p>
Turn yourself ONLINE to allow customers
to see your current delivery location.
</p>

</div>


<div class="card">

<div class="gps-box">

<strong>
GPS Status:
</strong>

<span id="gpsStatus">
Waiting for GPS permission...
</span>

</div>


<button
id="onlineButton"
class="green"
onclick="startTracking()">

GO ONLINE

</button>


<button
class="red"
onclick="stopTracking()">

GO OFFLINE

</button>


<div id="gpsDetails"
style="margin-top:15px">

Latitude:
<span id="lat">-</span>

<br>

Longitude:
<span id="lng">-</span>

<br>

Accuracy:
<span id="accuracy">-</span>

</div>

</div>


<div class="card">

<h2>
Assigned Deliveries
</h2>

<div id="driverDeliveries">
Loading...
</div>

</div>


<script>

let watchId = null;

let tracking = false;


function setStatus(text){

    document.getElementById(
        "gpsStatus"
    ).innerText = text;

}


function sendLocation(position){

    const latitude =
        position.coords.latitude;

    const longitude =
        position.coords.longitude;

    const accuracy =
        position.coords.accuracy;


    document.getElementById(
        "lat"
    ).innerText =
        latitude.toFixed(6);


    document.getElementById(
        "lng"
    ).innerText =
        longitude.toFixed(6);


    document.getElementById(
        "accuracy"
    ).innerText =
        Math.round(accuracy)
        + " metres";


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
        "accuracy",
        accuracy
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
    .then(response =>
        response.json()
    )
    .then(data => {

        if(data.success){

            setStatus(
                "GPS LIVE"
            );

        }else{

            setStatus(
                data.message ||
                "GPS update failed"
            );

        }

    })
    .catch(() => {

        setStatus(
            "Network error"
        );

    });

}


function gpsError(error){

    if(error.code === 1){

        setStatus(
            "GPS permission denied."
        );

    }else if(error.code === 2){

        setStatus(
            "GPS position unavailable."
        );

    }else{

        setStatus(
            "GPS timeout."
        );

    }

}


function startTracking(){

    if(!navigator.geolocation){

        setStatus(
            "This browser does not support GPS."
        );

        return;
    }


    tracking = true;


    const form =
        new URLSearchParams();

    form.append(
        "is_online",
        "true"
    );


    fetch(
        "/driver/status",
        {
            method:"POST",
            headers:{
                "Content-Type":
                "application/x-www-form-urlencoded"
            },
            body:form.toString()
        }
    );


    setStatus(
        "Requesting GPS permission..."
    );


    watchId =
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


function stopTracking(){

    if(watchId !== null){

        navigator.geolocation.clearWatch(
            watchId
        );

        watchId = null;

    }


    tracking = false;


    const form =
        new URLSearchParams();

    form.append(
        "is_online",
        "false"
    );


    fetch(
        "/driver/status",
        {
            method:"POST",
            headers:{
                "Content-Type":
                "application/x-www-form-urlencoded"
            },
            body:form.toString()
        }
    );


    setStatus(
        "OFFLINE"
    );

}


function loadDeliveries(){

    fetch(
        "/api/driver/deliveries"
    )
    .then(r => r.json())
    .then(data => {

        const box =
            document.getElementById(
                "driverDeliveries"
            );


        if(!data.success){

            box.innerHTML =
                "Unable to load deliveries.";

            return;

        }


        if(!data.deliveries.length){

            box.innerHTML =
                "No assigned deliveries.";

            return;

        }


        box.innerHTML =
            data.deliveries.map(
                d => `

                <div class="card">

                <h3>
                ${d.service_type}
                </h3>

                <p>
                Pickup:
                ${d.pickup_location}
                </p>

                <p>
                Destination:
                ${d.destination_location}
                </p>

                <p>
                Status:
                <span class="status">
                ${d.status}
                </span>
                </p>

                <a class="btn"
                href="/delivery/${d.id}/track">

                Open Live Map

                </a>

                </div>

                `
            ).join("");

    });

}


loadDeliveries();

setInterval(
    loadDeliveries,
    10000
);

</script>

"""

    return render_page(
        content,
        "Driver GPS"
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

        accuracy = float(
            request.form.get(
                "accuracy",
                0
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
                "GPS coordinates are invalid."
        }), 400


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
            longitude,
        "accuracy":
            accuracy,
        "updated_at":
            now_iso()
    })


# ============================================================
# DRIVER ONLINE / OFFLINE
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
        == "true"
    )

    rows, error = db_get(
        "driver_profiles",
        {
            "provider_id":
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

    result, update_error = db_update(
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
        "is_online":
            online
    })


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

    service_type = request.form.get(
        "service_type",
        "delivery"
    ).strip()


    if not pickup or not destination:

        flash(
            "Pickup and destination are required."
        )

        return redirect(
            url_for("drivers")
        )


    # Verify selected driver is approved
    # and online.

    if driver_id:

        driver_rows, driver_error = db_get(
            "driver_profiles",
            {
                "id":
                    f"eq.{driver_id}",

                "status":
                    "eq.approved",

                "is_online":
                    "eq.true",

                "select":
                    "id"
            }
        )

        if (
            driver_error
            or
            not driver_rows
        ):

            flash(
                "Selected driver is no longer online."
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
                "requested_at.desc"
        }
    )

    if error:

        rows = []

        flash(
            "Unable to load deliveries."
        )


    cards = ""

    for delivery in rows or []:

        delivery_id = delivery.get(
            "id"
        )

        cards += f"""

<div class="card">

<h3>
{(
    delivery.get("service_type")
    or "delivery"
).title()}
</h3>

<p>
<b>Pickup:</b>
{delivery.get("pickup_location")
or ""}
</p>

<p>
<b>Destination:</b>
{delivery.get("destination_location")
or ""}
</p>

<p>
<b>Status:</b>

<span class="status">
{delivery.get("status")
or "pending"}
</span>

</p>

<p>
<b>Requested:</b>
{delivery.get("requested_at")
or ""}
</p>

"""

        if delivery.get("driver_id"):

            cards += f"""

<a class="btn green"
href="/delivery/
{delivery_id}/track">

📍 Track Driver Live

</a>

"""

        cards += """

</div>

"""

    content = f"""

<div class="hero">

<h1>
My Deliveries
</h1>

<p>
Track your assigned driver's current
GPS position.
</p>

</div>

{cards or
'<div class="card">No delivery requests yet.</div>'}

"""

    return render_page(
        content,
        "My Deliveries"
    )


# ============================================================
# CUSTOMER LIVE TRACKING
# ============================================================

@app.route(
    "/delivery/<delivery_id>/track"
)
@login_required
def delivery_track(
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

    if not delivery.get("driver_id"):

        content = """

<div class="card">

<h2>
Driver Not Assigned
</h2>

<p>
The administrator has not assigned a
driver to this delivery yet.
</p>

<a class="btn"
href="/deliveries">
Back
</a>

</div>

"""

        return render_page(
            content,
            "Delivery Tracking"
        )


    content = f"""

<div class="hero">

<h1>
📍 Live Delivery Tracking
</h1>

<p>
Driver location updates automatically
while the driver is online.
</p>

</div>


<div class="card">

<h3>
Delivery
</h3>

<p>
<b>Pickup:</b>
{delivery.get("pickup_location") or ""}
</p>

<p>
<b>Destination:</b>
{delivery.get("destination_location") or ""}
</p>

<p>
<b>Status:</b>

<span id="deliveryStatus"
class="status">

{delivery.get("status") or ""}

</span>

</p>

<div class="gps-box">

<strong>
Driver GPS:
</strong>

<span id="gpsState">
Loading...
</span>

</div>

<div id="map"></div>

</div>


<script>

const deliveryId =
"{delivery_id}";


let map = L.map(
    "map"
).setView(
    [-13.9626,28.3228],
    6
);


L.tileLayer(
    "https://{{'{'}}s{{'}'}}.tile.openstreetmap.org/{{'{'}}z{{'}'}}/{{'{'}}x{{'}'}}/{{'{'}}y{{'}'}}.png",
    {
        maxZoom:19,
        attribution:
        "© OpenStreetMap"
    }
).addTo(map);


let driverMarker = null;


function updateMap(data){

    if(!data.success){

        document.getElementById(
            "gpsState"
        ).innerText =
            data.message ||
            "Driver GPS unavailable.";

        return;
    }


    document.getElementById(
        "gpsState"
    ).innerText =
        "LIVE — GPS updated "
        + data.updated_at;


    document.getElementById(
        "deliveryStatus"
    ).innerText =
        data.status;


    const lat =
        Number(data.latitude);

    const lng =
        Number(data.longitude);


    if(
        !Number.isFinite(lat)
        ||
        !Number.isFinite(lng)
    ){

        return;
    }


    if(!driverMarker){

        driverMarker =
            L.marker(
                [lat,lng]
            ).addTo(map);

        driverMarker.bindPopup(
            "🚗 Driver"
        );

    }else{

        driverMarker.setLatLng(
            [lat,lng]
        );

    }


    map.setView(
        [lat,lng],
        16
    );

}


function loadDriverLocation(){

    fetch(
        "/api/delivery/"
        + deliveryId
        + "/location"
    )
    .then(
        response =>
            response.json()
    )
    .then(
        updateMap
    )
    .catch(() => {

        document.getElementById(
            "gpsState"
        ).innerText =
            "Connection error.";

    });

}


loadDriverLocation();


setInterval(
    loadDriverLocation,
    5000
);

</script>

"""

    return render_page(
        content,
        "Live Delivery Tracking"
    )


# ============================================================
# CUSTOMER TRACKING API
# ============================================================

@app.route(
    "/api/delivery/<delivery_id>/location"
)
@login_required
def delivery_location_api(
    delivery_id
):

    uid = current_user()["id"]

    params = {
        "id":
            f"eq.{delivery_id}",
        "select":
            "id,customer_id,driver_id,status"
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

    driver_id = delivery.get(
        "driver_id"
    )

    if not driver_id:

        return jsonify({
            "success":
                False,
            "message":
                "Driver not assigned."
        })


    drivers, driver_error = db_get(
        "driver_profiles",
        {
            "id":
                f"eq.{driver_id}",

            "select":
                "id,vehicle_type,vehicle_number,"
                "latitude,longitude,is_online,"
                "location_name,last_location_update"
        }
    )

    if driver_error or not drivers:

        return jsonify({
            "success":
                False,
            "message":
                "Driver location unavailable."
        })


    driver = drivers[0]


    return jsonify({

        "success":
            True,

        "latitude":
            driver.get("latitude"),

        "longitude":
            driver.get("longitude"),

        "is_online":
            driver.get("is_online"),

        "location_name":
            driver.get("location_name"),

        "updated_at":
            driver.get(
                "last_location_update"
            ),

        "status":
            delivery.get("status"),

        "vehicle":
            driver.get("vehicle_type"),

        "vehicle_number":
            driver.get("vehicle_number")
    })


# ============================================================
# DRIVER DELIVERIES API
# ============================================================

@app.route(
    "/api/driver/deliveries"
)
@login_required
def driver_deliveries_api():

    uid = current_user()["id"]

    driver_rows, error = db_get(
        "driver_profiles",
        {
            "provider_id":
                f"eq.{uid}",
            "select":
                "id"
        }
    )

    if error or not driver_rows:

        return jsonify({
            "success":
                False,
            "deliveries":
                []
        })


    driver_id = driver_rows[0]["id"]


    rows, error = db_get(
        "delivery_requests",
        {
            "driver_id":
                f"eq.{driver_id}",

            "select":
                "*",

            "order":
                "requested_at.desc"
        }
    )

    if error:

        return jsonify({
            "success":
                False,
            "deliveries":
                []
        })


    deliveries = []

    for d in rows or []:

        deliveries.append({

            "id":
                d.get("id"),

            "service_type":
                d.get(
                    "service_type"
                )
                or "delivery",

            "pickup_location":
                d.get(
                    "pickup_location"
                )
                or "",

            "destination_location":
                d.get(
                    "destination_location"
                )
                or "",

            "status":
                d.get(
                    "status"
                )
                or "pending",

            "notes":
                d.get("notes")
                or ""
        })


    return jsonify({
        "success":
            True,
        "deliveries":
            deliveries
    })


# ============================================================
# DRIVER ACCEPT DELIVERY
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

    drivers, error = db_get(
        "driver_profiles",
        {
            "provider_id":
                f"eq.{uid}",
            "select":
                "id"
        }
    )

    if error or not drivers:

        return jsonify({
            "success":
                False,
            "message":
                "Driver profile not found."
        }), 404


    driver_id = drivers[0]["id"]


    deliveries, error = db_get(
        "delivery_requests",
        {
            "id":
                f"eq.{delivery_id}",

            "driver_id":
                f"eq.{driver_id}",

            "select":
                "id,status"
        }
    )

    if error or not deliveries:

        return jsonify({
            "success":
                False,
            "message":
                "Delivery not assigned to you."
        }), 403


    status = request.form.get(
        "status",
        "accepted"
    )


    allowed_statuses = {
        "accepted",
        "started",
        "completed",
        "cancelled"
    }


    if status not in allowed_statuses:

        return jsonify({
            "success":
                False,
            "message":
                "Invalid status."
        }), 400


    data = {
        "status":
            status,
        "updated_at":
            now_iso()
    }


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


    result, update_error = db_update(
        "delivery_requests",
        {
            "id":
                delivery_id,
            "driver_id":
                driver_id
        },
        data
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
        "status":
            status
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

    for d in rows or []:

        cards += f"""

<div class="card">

<h3>
🚗 {d.get("vehicle_type") or ""}
</h3>

<p>
Vehicle:
{d.get("vehicle_number") or ""}
</p>

<p>
License:
{d.get("license_number") or ""}
</p>

<p>
Status:
<span class="status">
{d.get("status") or ""}
</span>
</p>

<p>
GPS:
{d.get("latitude")
or "No latitude"}
,
{d.get("longitude")
or "No longitude"}
</p>

<p>
Online:
{d.get("is_online")}
</p>

<form method="POST"
action="/admin/drivers/{d.get("id")}">

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

<h1>
Driver Management
</h1>

</div>

<div class="grid">

{cards or
"<div class='card'>No drivers.</div>"}

</div>

"""

    return render_page(
        content,
        "Drivers Admin"
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


    if status not in {
        "pending",
        "approved",
        "rejected"
    }:

        status = "pending"


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
            "select":
                "*",
            "order":
                "requested_at.desc"
        }
    )

    cards = ""

    for d in rows or []:

        cards += f"""

<div class="card">

<h3>
{d.get("service_type")
or "Delivery"}
</h3>

<p>
Pickup:
{d.get("pickup_location")
or ""}
</p>

<p>
Destination:
{d.get("destination_location")
or ""}
</p>

<p>
Driver:
{d.get("driver_id")
or "Not assigned"}
</p>

<p>
Status:
<span class="status">
{d.get("status")
or ""}
</span>
</p>

<form method="POST"
action="/admin/deliveries/{d.get("id")}">

<label>
Assign Driver ID
</label>

<input
name="driver_id"
value="{d.get("driver_id") or ""}"
placeholder="Driver UUID">


<label>
Status
</label>

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

<button>
Update Delivery
</button>

</form>

"""

        if d.get("driver_id"):

            cards += f"""

<a class="btn green"
href="/delivery/
{d.get("id")}/track">

Open Live Map

</a>

"""

        cards += "</div>"


    content = f"""

<div class="hero">

<h1>
Delivery Management
</h1>

<p>
Assign drivers and manage delivery
status.
</p>

</div>

<div class="grid">

{cards or
"<div class='card'>No delivery requests.</div>"}

</div>

"""

    return render_page(
        content,
        "Delivery Admin"
    )


@app.route(
    "/admin/deliveries/<delivery_id>",
    methods=["POST"]
)
@admin_required
def admin_delivery_update(
    delivery_id
):

    driver_id = request.form.get(
        "driver_id",
        ""
    ).strip()


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


    if driver_id:

        drivers, driver_error = db_get(
            "driver_profiles",
            {
                "id":
                    f"eq.{driver_id}",
                "status":
                    "eq.approved",
                "select":
                    "id"
            }
        )

        if driver_error or not drivers:

            flash(
                "Driver ID is invalid or driver "
                "is not approved."
            )

            return redirect(
                url_for("admin_deliveries")
            )

        data["driver_id"] = driver_id

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
# PROFESSIONAL REGISTRATION
# ============================================================

@app.route(
    "/professionals/register",
    methods=["GET", "POST"]
)
@login_required
def professional_register():

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

            "profession":
                request.form.get(
                    "profession",
                    ""
                ).strip(),

            "specialty":
                request.form.get(
                    "specialty",
                    ""
                ).strip(),

            "description":
                request.form.get(
                    "description",
                    ""
                ).strip(),

            "available_days":
                request.form.get(
                    "available_days",
                    ""
                ).strip(),

            "start_time":
                request.form.get(
                    "start_time"
                ) or None,

            "end_time":
                request.form.get(
                    "end_time"
                ) or None,

            "status":
                "pending",

            "is_available":
                False
        }


        result, error = db_insert(
            "service_providers",
            data
        )


        if error:

            flash(
                "Professional registration failed: "
                + str(error)
            )

            return redirect(
                request.url
            )


        flash(
            "Professional registration submitted "
            "for approval."
        )


        return redirect(
            url_for("professionals")
        )


    content = """

<div class="card">

<h2>
Register Professional
</h2>

<form method="POST">

<label>
Full Name
</label>

<input
name="full_name"
required>


<label>
Phone
</label>

<input
name="phone"
required>


<label>
Profession
</label>

<select
name="profession"
required>

<option value="">
Select profession
</option>

<option>
Doctor
</option>

<option>
Lawyer
</option>

<option>
Teacher
</option>

<option>
Other
</option>

</select>


<label>
Specialty
</label>

<input
name="specialty">


<label>
Description
</label>

<textarea
name="description"></textarea>


<label>
Available Days
</label>

<input
name="available_days"
placeholder="Monday-Friday">


<label>
Start Time
</label>

<input
type="time"
name="start_time">


<label>
End Time
</label>

<input
type="time"
name="end_time">


<button class="orange">
Register
</button>

</form>

</div>

"""

    return render_page(
        content,
        "Professional Registration"
    )


# ============================================================
# PROFESSIONAL SEARCH
# ============================================================

@app.route("/professionals")
@login_required
def professionals():

    search = request.args.get(
        "q",
        ""
    ).strip()


    params = {

        "status":
            "eq.approved",

        "is_available":
            "eq.true",

        "select":
            "*",

        "order":
            "created_at.desc"
    }


    if search:

        params["or"] = (
            f"(full_name.ilike.*{search}*,"
            f"profession.ilike.*{search}*,"
            f"specialty.ilike.*{search}*)"
        )


    rows, error = db_get(
        "service_providers",
        params
    )


    cards = ""


    for p in rows or []:

        cards += f"""

<div class="card">

<h3>
{p.get("full_name") or ""}
</h3>

<p>
<b>Profession:</b>
{p.get("profession") or ""}
</p>

<p>
<b>Specialty:</b>
{p.get("specialty") or ""}
</p>

<p>
{p.get("description") or ""}
</p>

<p>
<b>Phone:</b>
{p.get("phone") or ""}
</p>

<p class="online">
● AVAILABLE
</p>

<a class="btn orange"
href="/professionals/
{p.get("id")}">

View & Book

</a>

</div>

"""


    content = f"""

<div class="hero">

<h1>
Professional Services
</h1>

<form method="GET">

<input
name="q"
value="{search}"
placeholder="Search professional...">

<button class="orange">
Search
</button>

</form>

<a class="btn dark"
href="/professionals/register">

Register Professional

</a>

</div>


<div class="grid">

{cards or
'<div class="card">No matching professionals found.</div>'}

</div>

"""


    return render_page(
        content,
        "Professionals"
    )


# ============================================================
# PROFESSIONAL DETAIL
# ============================================================

@app.route(
    "/professionals/<provider_id>",
    methods=["GET", "POST"]
)
@login_required
def professional_detail(
    provider_id
):

    rows, error = db_get(
        "service_providers",
        {
            "id":
                f"eq.{provider_id}",

            "status":
                "eq.approved",

            "select":
                "*"
        }
    )


    if error or not rows:

        flash(
            "Professional not found."
        )

        return redirect(
            url_for("professionals")
        )


    provider = rows[0]


    if request.method == "POST":

        booking = {

            "id":
                str(uuid.uuid4()),

            "customer_id":
                current_user()["id"],

            "provider_id":
                provider_id,

            "appointment_date":
                request.form.get(
                    "appointment_date"
                ),

            "start_time":
                request.form.get(
                    "start_time"
                ) or None,

            "end_time":
                request.form.get(
                    "end_time"
                ) or None,

            "location":
                request.form.get(
                    "location",
                    ""
                ).strip(),

            "notes":
                request.form.get(
                    "notes",
                    ""
                ).strip(),

            "status":
                "pending"
        }


        if not booking[
            "appointment_date"
        ]:

            flash(
                "Appointment date is required."
            )

            return redirect(
                request.url
            )


        result, booking_error = db_insert(
            "professional_bookings",
            booking
        )


        if booking_error:

            flash(
                "Booking failed: "
                + str(booking_error)
            )

            return redirect(
                request.url
            )


        flash(
            "Booking request submitted."
        )


        return redirect(
            url_for("my_bookings")
        )


    content = f"""

<div class="card">

<h2>
{provider.get("full_name") or ""}
</h2>

<p>
<b>Profession:</b>
{provider.get("profession") or ""}
</p>

<p>
<b>Specialty:</b>
{provider.get("specialty") or ""}
</p>

<p>
{provider.get("description") or ""}
</p>

<p>
<b>Phone:</b>
{provider.get("phone") or ""}
</p>

<p>
<b>Available:</b>
{provider.get("available_days") or ""}
</p>

</div>


<div class="card">

<h2>
Book Appointment
</h2>

<form method="POST">

<label>
Date
</label>

<input
type="date"
name="appointment_date"
required>


<label>
Start Time
</label>

<input
type="time"
name="start_time">


<label>
End Time
</label>

<input
type="time"
name="end_time">


<label>
Location
</label>

<input
name="location">


<label>
Notes
</label>

<textarea
name="notes"></textarea>


<button class="orange">
Send Booking Request
</button>

</form>

</div>

"""


    return render_page(
        content,
        "Professional"
    )


# ============================================================
# BOOKINGS
# ============================================================

@app.route("/bookings")
@login_required
def my_bookings():

    uid = current_user()["id"]

    rows, error = db_get(
        "professional_bookings",
        {
            "customer_id":
                f"eq.{uid}",

            "select":
                "*",

            "order":
                "created_at.desc"
        }
    )


    cards = ""


    for b in rows or []:

        cards += f"""

<div class="card">

<h3>
Professional Appointment
</h3>

<p>
Date:
{b.get("appointment_date") or ""}
</p>

<p>
Time:
{b.get("start_time") or ""}
-
{b.get("end_time") or ""}
</p>

<p>
Location:
{b.get("location") or ""}
</p>

<p>
Status:
<span class="status">
{b.get("status") or ""}
</span>
</p>

</div>

"""


    content = f"""

<div class="hero">

<h1>
My Bookings
</h1>

</div>

{cards or
'<div class="card">No bookings yet.</div>'}

"""


    return render_page(
        content,
        "Bookings"
    )


# ============================================================
# ADMIN PROFESSIONALS
# ============================================================

@app.route("/admin/professionals")
@admin_required
def admin_professionals():

    rows, error = db_get(
        "service_providers",
        {
            "select":
                "*",
            "order":
                "created_at.desc"
        }
    )


    cards = ""


    for p in rows or []:

        cards += f"""

<div class="card">

<h3>
{p.get("full_name") or ""}
</h3>

<p>
{p.get("profession") or ""}
-
{p.get("specialty") or ""}
</p>

<p>
Phone:
{p.get("phone") or ""}
</p>

<p>
Status:
{p.get("status") or ""}
</p>

<form method="POST"
action="/admin/professionals/
{p.get("id")}">

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

<label>

<input
type="checkbox"
name="is_available">

Available

</label>

<br><br>

<button>
Save
</button>

</form>

</div>

"""


    content = f"""

<div class="hero">

<h1>
Professional Management
</h1>

</div>

<div class="grid">

{cards or
"<div class='card'>No professionals.</div>"}

</div>

"""


    return render_page(
        content,
        "Professional Admin"
    )


@app.route(
    "/admin/professionals/<provider_id>",
    methods=["POST"]
)
@admin_required
def admin_professional_update(
    provider_id
):

    status = request.form.get(
        "status",
        "pending"
    )

    available = (
        "is_available"
        in request.form
    )


    result, error = db_update(
        "service_providers",
        {
            "id":
                provider_id
        },
        {
            "status":
                status,

            "is_available":
                available,

            "updated_at":
                now_iso()
        }
    )


    flash(
        "Professional updated."
        if not error
        else
        "Professional update failed."
    )


    return redirect(
        url_for("admin_professionals")
    )


# ============================================================
# ADMIN BOOKINGS
# ============================================================

@app.route("/admin/bookings")
@admin_required
def admin_bookings():

    rows, error = db_get(
        "professional_bookings",
        {
            "select":
                "*",

            "order":
                "created_at.desc"
        }
    )


    cards = ""


    for b in rows or []:

        cards += f"""

<div class="card">

<h3>
Professional Booking
</h3>

<p>
Customer:
{b.get("customer_id")}
</p>

<p>
Provider:
{b.get("provider_id")}
</p>

<p>
Date:
{b.get("appointment_date")}
</p>

<p>
Time:
{b.get("start_time") or ""}
-
{b.get("end_time") or ""}
</p>

<p>
Location:
{b.get("location") or ""}
</p>

<p>
Status:
{b.get("status") or ""}
</p>

<form method="POST"
action="/admin/bookings/
{b.get("id")}">

<select name="status">

<option value="pending">
Pending
</option>

<option value="accepted">
Accepted
</option>

<option value="completed">
Completed
</option>

<option value="cancelled">
Cancelled
</option>

</select>

<button>
Update
</button>

</form>

</div>

"""


    content = f"""

<div class="hero">

<h1>
Professional Bookings
</h1>

</div>

<div class="grid">

{cards or
"<div class='card'>No bookings.</div>"}

</div>

"""


    return render_page(
        content,
        "Booking Admin"
    )


@app.route(
    "/admin/bookings/<booking_id>",
    methods=["POST"]
)
@admin_required
def admin_booking_update(
    booking_id
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

        data["accepted_at"] = (
            now_iso()
        )

    elif status == "completed":

        data["completed_at"] = (
            now_iso()
        )


    result, error = db_update(
        "professional_bookings",
        {
            "id":
                booking_id
        },
        data
    )


    flash(
        "Booking updated."
        if not error
        else
        "Booking update failed."
    )


    return redirect(
        url_for("admin_bookings")
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

        "version":
            "GPS-ASSIGNMENTS-PRO",

        "services": [

            "assignments",

            "drivers",

            "delivery",

            "live_gps_tracking",

            "professional_services"

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
Page not found
</h2>

<a class="btn"
href="/">
Home
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
Internal Server Error
</h2>

<p>
The server encountered an unexpected
error. Check the Render logs.
</p>

<a class="btn"
href="/">
Home
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

import os
import uuid
import logging
from datetime import datetime, timezone
from functools import wraps

import requests
from flask import (
    Flask, request, redirect, url_for, session,
    render_template_string, flash, jsonify, send_file
)
from werkzeug.utils import secure_filename
from io import BytesIO
from dotenv import load_dotenv

load_dotenv()

# ============================================================
# KOJA AFRICA - PRODUCTION APP
# ============================================================

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "CHANGE_THIS_SECRET")

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
SUPABASE_BUCKET = os.getenv("SUPABASE_BUCKET", "koja-files")

ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "").strip().lower()

ALLOWED_EXTENSIONS = {
    "pdf", "doc", "docx", "jpg", "jpeg", "png", "webp"
}

MAX_FILE_SIZE = 15 * 1024 * 1024

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("koja")


# ============================================================
# BASIC VALIDATION
# ============================================================

def configuration_ok():
    return bool(
        SUPABASE_URL and
        SUPABASE_SERVICE_KEY
    )


def api_headers(prefer=None):
    h = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
    }

    if prefer:
        h["Prefer"] = prefer

    return h


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def allowed_file(filename):
    if not filename or "." not in filename:
        return False

    ext = filename.rsplit(".", 1)[1].lower()

    return ext in ALLOWED_EXTENSIONS


# ============================================================
# SUPABASE DATABASE
# ============================================================

def db_get(table, params=None):
    try:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/{table}",
            headers=api_headers(),
            params=params or {},
            timeout=30
        )

        if not r.ok:
            logger.error(
                "GET %s: %s",
                table,
                r.text
            )
            return None, r.text

        return r.json(), None

    except Exception as e:
        logger.exception("Supabase GET error")
        return None, str(e)


def db_insert(table, data):
    try:
        r = requests.post(
            f"{SUPABASE_URL}/rest/v1/{table}",
            headers=api_headers("return=representation"),
            json=data,
            timeout=30
        )

        if not r.ok:
            logger.error(
                "INSERT %s: %s",
                table,
                r.text
            )
            return None, r.text

        try:
            return r.json(), None
        except Exception:
            return [], None

    except Exception as e:
        logger.exception("Supabase INSERT error")
        return None, str(e)


def db_update(table, filters, data):
    params = {}

    for key, value in filters.items():
        params[key] = f"eq.{value}"

    try:
        r = requests.patch(
            f"{SUPABASE_URL}/rest/v1/{table}",
            headers=api_headers("return=representation"),
            params=params,
            json=data,
            timeout=30
        )

        if not r.ok:
            logger.error(
                "UPDATE %s: %s",
                table,
                r.text
            )
            return None, r.text

        try:
            return r.json(), None
        except Exception:
            return [], None

    except Exception as e:
        logger.exception("Supabase UPDATE error")
        return None, str(e)


# ============================================================
# SUPABASE AUTH
# ============================================================

def auth_signup(email, password):
    try:
        r = requests.post(
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

        if not r.ok:
            logger.error("SIGNUP: %s", r.text)
            return None, r.text

        return r.json(), None

    except Exception as e:
        return None, str(e)


def auth_login(email, password):
    try:
        r = requests.post(
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

        if not r.ok:
            logger.error("LOGIN: %s", r.text)
            return None, r.text

        return r.json(), None

    except Exception as e:
        return None, str(e)


# ============================================================
# SUPABASE STORAGE
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

    extension = filename.rsplit(".", 1)[1].lower()

    object_name = (
        f"{folder}/"
        f"{uuid.uuid4().hex}."
        f"{extension}"
    )

    content_type = (
        file_storage.mimetype or
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
        r = requests.post(
            f"{SUPABASE_URL}/storage/v1/object/"
            f"{SUPABASE_BUCKET}/{object_name}",
            headers=headers,
            data=content,
            timeout=60
        )

        if not r.ok:
            logger.error(
                "STORAGE UPLOAD: %s",
                r.text
            )
            return None, r.text

        return {
            "path": object_name,
            "filename": filename,
            "content_type": content_type,
            "size": len(content)
        }, None

    except Exception as e:
        logger.exception("Storage error")
        return None, str(e)


def storage_download(path):
    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization":
            f"Bearer {SUPABASE_SERVICE_KEY}"
    }

    try:
        r = requests.get(
            f"{SUPABASE_URL}/storage/v1/object/"
            f"{SUPABASE_BUCKET}/{path}",
            headers=headers,
            timeout=60
        )

        if not r.ok:
            return None, r.text

        return r.content, None

    except Exception as e:
        return None, str(e)


# ============================================================
# SESSION
# ============================================================

def user():
    return session.get("user")


def logged_in():
    return bool(user())


def is_admin():
    u = user()

    if not u:
        return False

    return (
        u.get("email", "").lower()
        == ADMIN_EMAIL
        and ADMIN_EMAIL != ""
    )


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not logged_in():
            flash("Please login first.")
            return redirect(url_for("login"))
        return fn(*args, **kwargs)

    return wrapper


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not logged_in():
            return redirect(url_for("login"))

        if not is_admin():
            flash("Administrator access required.")
            return redirect(url_for("dashboard"))

        return fn(*args, **kwargs)

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
      content="width=device-width,initial-scale=1">

<title>{{ title }} - KOJA AFRICA</title>

<style>
*{box-sizing:border-box}

body{
 margin:0;
 background:#f3f6fa;
 color:#172033;
 font-family:Arial,sans-serif;
}

nav{
 background:#111827;
 color:white;
 padding:14px;
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
 max-width:1100px;
 margin:auto;
 padding:20px;
}

.hero{
 background:linear-gradient(135deg,#0f766e,#2563eb);
 color:white;
 padding:30px;
 border-radius:18px;
 margin-bottom:20px;
}

.grid{
 display:grid;
 grid-template-columns:
 repeat(auto-fit,minmax(260px,1fr));
 gap:18px;
}

.card{
 background:white;
 padding:20px;
 margin-bottom:18px;
 border-radius:15px;
 box-shadow:0 3px 12px rgba(0,0,0,.07);
}

input,textarea,select{
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

button,.btn{
 border:0;
 border-radius:9px;
 padding:11px 17px;
 background:#2563eb;
 color:white;
 text-decoration:none;
 cursor:pointer;
 display:inline-block;
}

.green{background:#059669}
.orange{background:#d97706}
.red{background:#dc2626}
.dark{background:#111827}

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

footer{
 text-align:center;
 padding:30px;
 color:#6b7280;
}
</style>
</head>

<body>

<nav>
<span class="brand">KOJA AFRICA</span><br>

<a href="/">Home</a>

{% if session.get("user") %}

<a href="/dashboard">Dashboard</a>
<a href="/assignments">Assignments</a>
<a href="/drivers">Drivers</a>
<a href="/deliveries">My Deliveries</a>
<a href="/professionals">Professionals</a>

{% if is_admin_user %}
<a href="/admin">Admin</a>
{% endif %}

<a href="/logout">Logout</a>

{% else %}

<a href="/login">Login</a>
<a href="/register">Create Account</a>

{% endif %}
</nav>

<div class="container">

{% with messages=get_flashed_messages() %}
{% for message in messages %}
<div class="flash">{{ message }}</div>
{% endfor %}
{% endwith %}

{{ content|safe }}

</div>

<footer>
KOJA AFRICA<br>
Assignments • Drivers & Delivery • Professional Services
</footer>

</body>
</html>
"""


def render_page(content, title="KOJA AFRICA"):
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
Academic assistance, drivers and delivery,
and professional services in one platform.
</p>

<a class="btn" href="/register">
Create Account
</a>

<a class="btn dark" href="/login">
Login
</a>
</div>

<div class="grid">

<div class="card">
<h2>📚 Assignments</h2>
<p>
Submit academic questions to KOJA,
track their progress and receive answers.
</p>
<a class="btn" href="/assignments">
Open Assignments
</a>
</div>

<div class="card">
<h2>🚗 Drivers & Delivery</h2>
<p>
Find available drivers by their current
location and request a ride or delivery.
</p>
<a class="btn green" href="/drivers">
Find Drivers
</a>
</div>

<div class="card">
<h2>👨‍⚕️ Professional Services</h2>
<p>
Find doctors, lawyers, teachers and
other registered professionals.
</p>
<a class="btn orange" href="/professionals">
Find Professionals
</a>
</div>

</div>
"""

    return render_page(content)


# ============================================================
# REGISTER
# ============================================================

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        email = request.form.get(
            "email", ""
        ).strip().lower()

        password = request.form.get(
            "password", ""
        )

        if not email or not password:
            flash("Email and password are required.")
            return redirect(url_for("register"))

        if len(password) < 6:
            flash("Password must contain at least 6 characters.")
            return redirect(url_for("register"))

        result, error = auth_signup(
            email,
            password
        )

        if error:
            flash(
                "Registration failed. "
                + str(error)
            )
            return redirect(url_for("register"))

        flash(
            "Account created successfully. "
            "You can now login."
        )

        return redirect(url_for("login"))

    content = """
<div class="card">
<h2>Create Account</h2>

<form method="POST">

<label>Email</label>
<input type="email"
       name="email"
       required>

<label>Password</label>
<input type="password"
       name="password"
       minlength="6"
       required>

<button>Create Account</button>

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

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form.get(
            "email", ""
        ).strip().lower()

        password = request.form.get(
            "password", ""
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
            return redirect(url_for("login"))

        auth_user = result.get("user") or {}

        session["user"] = {
            "id": auth_user.get("id"),
            "email": (
                auth_user.get("email")
                or email
            )
        }

        session.permanent = True

        return redirect(url_for("dashboard"))

    content = """
<div class="card">
<h2>Login</h2>

<form method="POST">

<label>Email</label>
<input type="email"
       name="email"
       required>

<label>Password</label>
<input type="password"
       name="password"
       required>

<button>Login</button>

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

    return redirect(url_for("home"))


# ============================================================
# DASHBOARD
# ============================================================

@app.route("/dashboard")
@login_required
def dashboard():

    u = user()

    content = f"""
<div class="hero">
<h1>Dashboard</h1>
<p>{u.get("email")}</p>
</div>

<div class="grid">

<div class="card">
<h2>📚 Assignments</h2>
<a class="btn"
   href="/assignments/new">
New Assignment
</a>
</div>

<div class="card">
<h2>🚗 Drivers</h2>
<a class="btn green"
   href="/drivers">
Find Driver
</a>
</div>

<div class="card">
<h2>📦 Deliveries</h2>
<a class="btn green"
   href="/deliveries">
My Requests
</a>
</div>

<div class="card">
<h2>👨‍⚕️ Professionals</h2>
<a class="btn orange"
   href="/professionals">
Find Professional
</a>
</div>

<div class="card">
<h2>Register as Driver</h2>
<a class="btn"
   href="/drivers/register">
Register
</a>
</div>

<div class="card">
<h2>Register as Professional</h2>
<a class="btn orange"
   href="/professionals/register">
Register
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

    uid = user()["id"]

    rows, error = db_get(
        "assignments",
        {
            "student_id": f"eq.{uid}",
            "select": "*",
            "order": "created_at.desc"
        }
    )

    if error:
        flash("Unable to load assignments.")
        rows = []

    html = ""

    for a in rows or []:

        html += f"""
<div class="card">

<h3>{a.get("title") or "Assignment"}</h3>

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

<a class="btn"
   href="/assignments/{a.get("id")}">
View Assignment
</a>

</div>
"""

    content = f"""
<div class="hero">
<h1>Assignments</h1>

<a class="btn"
   href="/assignments/new">
New Assignment
</a>
</div>

{html or '<div class="card">No assignments yet.</div>'}
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

        uid = user()["id"]

        title = request.form.get(
            "title", ""
        ).strip()

        subject = request.form.get(
            "subject", ""
        ).strip()

        description = request.form.get(
            "description", ""
        ).strip()

        file = request.files.get("question_file")

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
                    "Question file upload failed: "
                    + str(error)
                )
                return redirect(
                    url_for("new_assignment")
                )

        # The assignment table has no file columns.
        # File metadata is therefore stored in the
        # admin_note field as JSON-like text.
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

<h2>New Assignment</h2>

<form method="POST"
      enctype="multipart/form-data">

<label>Title</label>
<input name="title"
       required>

<label>Subject</label>
<input name="subject"
       required>

<label>Question</label>
<textarea name="description"
          required></textarea>

<label>
Question PDF / Word / Image
</label>

<input type="file"
       name="question_file"
       accept=".pdf,.doc,.docx,.jpg,.jpeg,.png,.webp">

<button>
Send to Admin
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


@app.route("/assignments/<assignment_id>")
@login_required
def assignment_detail(assignment_id):

    uid = user()["id"]

    rows, error = db_get(
        "assignments",
        {
            "id": f"eq.{assignment_id}",
            "student_id": f"eq.{uid}",
            "select": "*"
        }
    )

    if error or not rows:
        flash("Assignment not found.")
        return redirect(url_for("assignments"))

    a = rows[0]

    content = f"""
<div class="card">

<h2>{a.get("title") or ""}</h2>

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

<h3>Question</h3>

<p>
{a.get("description") or ""}
</p>

</div>

<div class="card">

<h2>Answer</h2>

<p>
{a.get("answer_text") or
"Your answer has not been completed yet."}
</p>

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
            "select": "*",
            "order": "created_at.desc"
        }
    )

    html = ""

    for a in rows or []:

        html += f"""
<div class="card">

<h3>{a.get("title") or ""}</h3>

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
   href="/admin/assignments/{a.get("id")}">
Process
</a>

</div>
"""

    content = f"""
<div class="hero">
<h1>KOJA Admin</h1>

<p>
Manage assignments, drivers,
deliveries and professionals.
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

</div>

{html or "<div class='card'>No assignments.</div>"}
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
def admin_assignment(assignment_id):

    rows, error = db_get(
        "assignments",
        {
            "id": f"eq.{assignment_id}",
            "select": "*"
        }
    )

    if error or not rows:
        flash("Assignment not found.")
        return redirect(url_for("admin"))

    a = rows[0]

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

            note += (
                "\nANSWER_FILE|"
                + info["path"]
                + "|"
                + info["filename"]
                + "|"
                + info["content_type"]
            )

        data = {
            "status": status,
            "admin_note": note,
            "answer_text": answer_text,
            "updated_at": now_iso()
        }

        if status in (
            "completed",
            "approved"
        ):
            data["completed_at"] = now_iso()

        result, update_error = db_update(
            "assignments",
            {"id": assignment_id},
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

        return redirect(request.url)

    content = f"""
<div class="card">

<h2>{a.get("title") or ""}</h2>

<p>
<b>Student:</b>
{a.get("student_id")}
</p>

<p>
<b>Subject:</b>
{a.get("subject") or ""}
</p>

<hr>

<h3>Question</h3>

<p>
{a.get("description") or ""}
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

<label>Admin Note</label>

<textarea name="admin_note">
{a.get("admin_note") or ""}
</textarea>

<label>Written Answer</label>

<textarea name="answer_text">
{a.get("answer_text") or ""}
</textarea>

<label>Answer PDF / Word</label>

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
# FILE DOWNLOAD
# ============================================================

@app.route(
    "/assignment-file/<assignment_id>/<file_type>"
)
@login_required
def assignment_file(assignment_id, file_type):

    uid = user()["id"]

    params = {
        "id": f"eq.{assignment_id}",
        "select": "*"
    }

    if not is_admin():
        params["student_id"] = f"eq.{uid}"

    rows, error = db_get(
        "assignments",
        params
    )

    if error or not rows:
        return "File not found", 404

    a = rows[0]

    note = a.get("admin_note") or ""

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

    content, download_error = storage_download(path)

    if download_error:
        return "Unable to download file", 500

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

    uid = user()["id"]

    if request.method == "POST":

        data = {
            "id": str(uuid.uuid4()),
            "provider_id": uid,
            "vehicle_type":
                request.form.get(
                    "vehicle_type", ""
                ).strip(),
            "vehicle_number":
                request.form.get(
                    "vehicle_number", ""
                ).strip(),
            "license_number":
                request.form.get(
                    "license_number", ""
                ).strip(),
            "status": "pending",
            "is_online": False,
            "latitude": None,
            "longitude": None,
            "location_name":
                request.form.get(
                    "location_name", ""
                ).strip()
        }

        if not data["vehicle_type"]:
            flash("Vehicle type is required.")
            return redirect(request.url)

        result, error = db_insert(
            "driver_profiles",
            data
        )

        if error:
            flash(
                "Driver registration failed: "
                + str(error)
            )
            return redirect(request.url)

        flash(
            "Driver registration submitted "
            "for admin approval."
        )

        return redirect(url_for("drivers"))

    content = """
<div class="card">

<h2>Driver Registration</h2>

<form method="POST">

<label>Vehicle Type</label>
<input name="vehicle_type"
       placeholder="Car, motorcycle, van..."
       required>

<label>Vehicle Number</label>
<input name="vehicle_number"
       required>

<label>License Number</label>
<input name="license_number"
       required>

<label>Exact Location Name</label>
<input name="location_name"
       placeholder="Example: Kitwe City Square"
       required>

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
            "status": "eq.approved",
            "is_online": "eq.true",
            "select": "*",
            "order": "last_location_update.desc"
        }
    )

    if error:
        flash("Could not load drivers.")
        rows = []

    cards = ""

    for d in rows or []:

        cards += f"""
<div class="card">

<h3>
🚗 {d.get("vehicle_type") or "Driver"}
</h3>

<p>
Vehicle:
{d.get("vehicle_number") or ""}
</p>

<p class="location">
📍 {d.get("location_name")
    or "Location name unavailable"}
</p>

<p class="online">
● ONLINE
</p>

<form method="POST"
      action="/delivery/request">

<input type="hidden"
       name="driver_id"
       value="{d.get("id")}">

<input type="hidden"
       name="service_type"
       value="delivery">

<label>Pickup</label>
<input name="pickup_location"
       placeholder="Exact pickup location"
       required>

<label>Destination</label>
<input name="destination_location"
       placeholder="Exact destination"
       required>

<label>Notes</label>
<textarea name="notes"
          placeholder="Instructions"></textarea>

<button class="green">
Request Driver
</button>

</form>

</div>
"""

    content = f"""
<div class="hero">

<h1>Available Drivers</h1>

<p>
Drivers who have been approved and are
currently online appear here.
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
# DRIVER GPS
# ============================================================

@app.route(
    "/driver/location",
    methods=["POST"]
)
@login_required
def driver_location():

    uid = user()["id"]

    rows, error = db_get(
        "driver_profiles",
        {
            "provider_id": f"eq.{uid}",
            "select": "id"
        }
    )

    if error or not rows:
        return jsonify({
            "success": False,
            "message": "Driver profile not found."
        }), 404

    driver_id = rows[0]["id"]

    try:
        latitude = float(
            request.form.get("latitude")
        )

        longitude = float(
            request.form.get("longitude")
        )

    except Exception:
        return jsonify({
            "success": False,
            "message": "Invalid GPS coordinates."
        }), 400

    location_name = request.form.get(
        "location_name",
        ""
    ).strip()

    result, error = db_update(
        "driver_profiles",
        {"id": driver_id},
        {
            "latitude": latitude,
            "longitude": longitude,
            "location_name": location_name,
            "is_online": True,
            "last_location_update": now_iso(),
            "updated_at": now_iso()
        }
    )

    if error:
        return jsonify({
            "success": False,
            "message": error
        }), 500

    return jsonify({
        "success": True,
        "location_name": location_name
    })


@app.route(
    "/driver/status",
    methods=["POST"]
)
@login_required
def driver_status():

    uid = user()["id"]

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
            "provider_id": f"eq.{uid}",
            "select": "id"
        }
    )

    if error or not rows:
        flash("Driver profile not found.")
        return redirect(url_for("drivers"))

    db_update(
        "driver_profiles",
        {"id": rows[0]["id"]},
        {
            "is_online": online,
            "updated_at": now_iso()
        }
    )

    flash(
        "Driver is now "
        + ("ONLINE." if online else "OFFLINE.")
    )

    return redirect(url_for("drivers"))


# ============================================================
# DELIVERY REQUEST
# ============================================================

@app.route(
    "/delivery/request",
    methods=["POST"]
)
@login_required
def delivery_request():

    uid = user()["id"]

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
        return redirect(url_for("drivers"))

    data = {
        "id": str(uuid.uuid4()),
        "customer_id": uid,
        "driver_id": driver_id,
        "pickup_location": pickup,
        "delivery_location": destination,
        "latitude": None,
        "longitude": None,
        "status": "pending",
        "notes": notes,
        "service_type": service_type,
        "destination_location": destination,
        "pickup_latitude": None,
        "pickup_longitude": None,
        "destination_latitude": None,
        "destination_longitude": None,
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
        return redirect(url_for("drivers"))

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

    uid = user()["id"]

    rows, error = db_get(
        "delivery_requests",
        {
            "customer_id": f"eq.{uid}",
            "select": "*",
            "order": "created_at.desc"
        }
    )

    cards = ""

    for d in rows or []:

        cards += f"""
<div class="card">

<h3>
{(d.get("service_type") or "delivery").title()}
</h3>

<p>
<b>Pickup:</b>
{d.get("pickup_location") or ""}
</p>

<p>
<b>Destination:</b>
{d.get("destination_location") or ""}
</p>

<p>
<b>Status:</b>
<span class="status">
{d.get("status") or "pending"}
</span>
</p>

<p>
<b>Requested:</b>
{d.get("requested_at")
 or d.get("created_at") or ""}
</p>

</div>
"""

    content = f"""
<div class="hero">
<h1>My Deliveries</h1>
</div>

{cards or
'<div class="card">No delivery requests yet.</div>'}
"""

    return render_page(
        content,
        "My Deliveries"
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

    uid = user()["id"]

    if request.method == "POST":

        data = {
            "id": str(uuid.uuid4()),
            "user_id": uid,
            "full_name":
                request.form.get(
                    "full_name", ""
                ).strip(),
            "phone":
                request.form.get(
                    "phone", ""
                ).strip(),
            "email": user()["email"],
            "profession":
                request.form.get(
                    "profession", ""
                ).strip(),
            "specialty":
                request.form.get(
                    "specialty", ""
                ).strip(),
            "description":
                request.form.get(
                    "description", ""
                ).strip(),
            "available_days":
                request.form.get(
                    "available_days", ""
                ).strip(),
            "start_time":
                request.form.get(
                    "start_time"
                ) or None,
            "end_time":
                request.form.get(
                    "end_time"
                ) or None,
            "status": "pending",
            "is_available": False
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
            return redirect(request.url)

        flash(
            "Professional registration submitted "
            "for approval."
        )

        return redirect(
            url_for("professionals")
        )

    content = """
<div class="card">

<h2>Register Professional Service</h2>

<form method="POST">

<label>Full Name</label>
<input name="full_name"
       required>

<label>Phone</label>
<input name="phone"
       required>

<label>Profession</label>

<select name="profession"
        required>

<option value="">
Select profession
</option>

<option>Doctor</option>
<option>Lawyer</option>
<option>Teacher</option>
<option>Other</option>

</select>

<label>Specialty</label>
<input name="specialty">

<label>Description</label>
<textarea name="description"></textarea>

<label>Available Days</label>
<input name="available_days"
       placeholder="Monday-Friday">

<label>Start Time</label>
<input type="time"
       name="start_time">

<label>End Time</label>
<input type="time"
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
        "status": "eq.approved",
        "is_available": "eq.true",
        "select": "*",
        "order": "created_at.desc"
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
   href="/professionals/{p.get("id")}">
View & Book
</a>

</div>
"""

    content = f"""
<div class="hero">

<h1>Professional Services</h1>

<form method="GET">

<input name="q"
       value="{search}"
       placeholder="Search doctor, lawyer, teacher...">

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
# PROFESSIONAL PROFILE + BOOKING
# ============================================================

@app.route(
    "/professionals/<provider_id>",
    methods=["GET", "POST"]
)
@login_required
def professional_detail(provider_id):

    rows, error = db_get(
        "service_providers",
        {
            "id": f"eq.{provider_id}",
            "status": "eq.approved",
            "select": "*"
        }
    )

    if error or not rows:
        flash("Professional not found.")
        return redirect(url_for("professionals"))

    p = rows[0]

    if request.method == "POST":

        booking = {
            "id": str(uuid.uuid4()),
            "customer_id": user()["id"],
            "provider_id": provider_id,
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
                    "location", ""
                ).strip(),
            "notes":
                request.form.get(
                    "notes", ""
                ).strip(),
            "status": "pending"
        }

        if not booking["appointment_date"]:
            flash("Appointment date is required.")
            return redirect(request.url)

        result, booking_error = db_insert(
            "professional_bookings",
            booking
        )

        if booking_error:
            flash(
                "Booking failed: "
                + str(booking_error)
            )
            return redirect(request.url)

        flash(
            "Booking request submitted."
        )

        return redirect(
            url_for("my_bookings")
        )

    content = f"""
<div class="card">

<h2>
{p.get("full_name") or ""}
</h2>

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

<p>
<b>Available:</b>
{p.get("available_days") or ""}
</p>

<p>
<b>Hours:</b>
{p.get("start_time") or ""}
-
{p.get("end_time") or ""}
</p>

</div>

<div class="card">

<h2>Book Appointment</h2>

<form method="POST">

<label>Date</label>

<input type="date"
       name="appointment_date"
       required>

<label>Start Time</label>

<input type="time"
       name="start_time">

<label>End Time</label>

<input type="time"
       name="end_time">

<label>Location</label>

<input name="location"
       placeholder="Exact meeting location">

<label>Notes</label>

<textarea name="notes"
          placeholder="Explain what you need"></textarea>

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
# CUSTOMER BOOKINGS
# ============================================================

@app.route("/bookings")
@login_required
def my_bookings():

    uid = user()["id"]

    rows, error = db_get(
        "professional_bookings",
        {
            "customer_id": f"eq.{uid}",
            "select": "*",
            "order": "created_at.desc"
        }
    )

    cards = ""

    for b in rows or []:

        cards += f"""
<div class="card">

<h3>
Appointment
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
{b.get("status") or "pending"}
</span>
</p>

</div>
"""

    content = f"""
<div class="hero">
<h1>My Professional Bookings</h1>
</div>

{cards or
'<div class="card">No bookings yet.</div>'}
"""

    return render_page(
        content,
        "Bookings"
    )


# ============================================================
# ADMIN DRIVER MANAGEMENT
# ============================================================

@app.route("/admin/drivers")
@admin_required
def admin_drivers():

    rows, error = db_get(
        "driver_profiles",
        {
            "select": "*",
            "order": "created_at.desc"
        }
    )

    cards = ""

    for d in rows or []:

        cards += f"""
<div class="card">

<h3>
{d.get("vehicle_type") or ""}
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
Location:
{d.get("location_name") or ""}
</p>

<p>
Status:
{d.get("status") or ""}
</p>

<form method="POST"
      action="/admin/drivers/{d.get("id")}">

<select name="status">

<option value="pending">Pending</option>
<option value="approved">Approved</option>
<option value="rejected">Rejected</option>

</select>

<button>
Save
</button>

</form>

</div>
"""

    content = f"""
<div class="hero">
<h1>Driver Management</h1>
</div>

<div class="grid">
{cards or "<div class='card'>No drivers.</div>"}
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
def admin_driver_update(driver_id):

    status = request.form.get(
        "status",
        "pending"
    )

    result, error = db_update(
        "driver_profiles",
        {"id": driver_id},
        {
            "status": status,
            "updated_at": now_iso()
        }
    )

    flash(
        "Driver updated."
        if not error
        else "Driver update failed."
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
            "select": "*",
            "order": "created_at.desc"
        }
    )

    cards = ""

    for d in rows or []:

        cards += f"""
<div class="card">

<h3>
{d.get("service_type") or "Delivery"}
</h3>

<p>
Pickup:
{d.get("pickup_location") or ""}
</p>

<p>
Destination:
{d.get("destination_location") or ""}
</p>

<p>
Driver:
{d.get("driver_id") or "Not assigned"}
</p>

<p>
Status:
{d.get("status") or ""}
</p>

<form method="POST"
      action="/admin/deliveries/{d.get("id")}">

<select name="status">

<option value="pending">Pending</option>
<option value="accepted">Accepted</option>
<option value="started">Started</option>
<option value="completed">Completed</option>
<option value="cancelled">Cancelled</option>

</select>

<button>
Update
</button>

</form>

</div>
"""

    content = f"""
<div class="hero">
<h1>Delivery Management</h1>
</div>

<div class="grid">
{cards or "<div class='card'>No requests.</div>"}
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
def admin_delivery_update(delivery_id):

    status = request.form.get(
        "status",
        "pending"
    )

    data = {
        "status": status,
        "updated_at": now_iso()
    }

    if status == "accepted":
        data["accepted_at"] = now_iso()

    elif status == "started":
        data["started_at"] = now_iso()

    elif status == "completed":
        data["completed_at"] = now_iso()

    result, error = db_update(
        "delivery_requests",
        {"id": delivery_id},
        data
    )

    flash(
        "Delivery updated."
        if not error
        else "Delivery update failed."
    )

    return redirect(
        url_for("admin_deliveries")
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
            "select": "*",
            "order": "created_at.desc"
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
      action="/admin/professionals/{p.get("id")}">

<select name="status">

<option value="pending">Pending</option>
<option value="approved">Approved</option>
<option value="rejected">Rejected</option>

</select>

<label>
<input type="checkbox"
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
<h1>Professional Management</h1>
</div>

<div class="grid">
{cards or "<div class='card'>No professionals.</div>"}
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
def admin_professional_update(provider_id):

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
        {"id": provider_id},
        {
            "status": status,
            "is_available": available,
            "updated_at": now_iso()
        }
    )

    flash(
        "Professional updated."
        if not error
        else "Professional update failed."
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
            "select": "*",
            "order": "created_at.desc"
        }
    )

    cards = ""

    for b in rows or []:

        cards += f"""
<div class="card">

<h3>Professional Booking</h3>

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
{b.get("status")}
</p>

<form method="POST"
      action="/admin/bookings/{b.get("id")}">

<select name="status">

<option value="pending">Pending</option>
<option value="accepted">Accepted</option>
<option value="completed">Completed</option>
<option value="cancelled">Cancelled</option>

</select>

<button>
Update
</button>

</form>

</div>
"""

    content = f"""
<div class="hero">
<h1>Professional Bookings</h1>
</div>

<div class="grid">
{cards or "<div class='card'>No bookings.</div>"}
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
def admin_booking_update(booking_id):

    status = request.form.get(
        "status",
        "pending"
    )

    data = {
        "status": status,
        "updated_at": now_iso()
    }

    if status == "accepted":
        data["accepted_at"] = now_iso()

    elif status == "completed":
        data["completed_at"] = now_iso()

    result, error = db_update(
        "professional_bookings",
        {"id": booking_id},
        data
    )

    flash(
        "Booking updated."
        if not error
        else "Booking update failed."
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
        "status": "ok",
        "application": "KOJA AFRICA",
        "services": [
            "assignments",
            "drivers_delivery",
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
<h2>Page not found</h2>
<a class="btn" href="/">
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
<h2>Internal Server Error</h2>
<p>
The server encountered an unexpected error.
Check the Render logs for the exact error.
</p>
<a class="btn" href="/">
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
        os.getenv("PORT", "5000")
    )

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )

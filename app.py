import os
import io
import uuid
import secrets
from datetime import datetime, timezone
from functools import wraps

import requests
from dotenv import load_dotenv
from flask import (
    Flask, request, redirect, url_for, session,
    render_template_string, flash, send_file, abort
)
from werkzeug.security import generate_password_hash, check_password_hash

load_dotenv()

# ============================================================
# KOJA AFRICA
# Client submits work -> KOJA processes it -> KOJA returns
# the finished document.
#
# Stack:
#   Flask + Supabase REST API + Supabase Storage
#   Deployable on Render.
#
# Required environment variables:
#   SUPABASE_URL
#   SUPABASE_SERVICE_KEY
#   SECRET_KEY
#   ADMIN_EMAIL
#   ADMIN_PASSWORD
#
# Optional:
#   STORAGE_BUCKET=koja-files
#   MAX_FILE_MB=20
# ============================================================

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY") or secrets.token_hex(32)

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
STORAGE_BUCKET = os.getenv("STORAGE_BUCKET", "koja-files")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@koja-africa.com").strip().lower()
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "change-this-password")
MAX_FILE_MB = int(os.getenv("MAX_FILE_MB", "20"))
MAX_CONTENT_LENGTH = MAX_FILE_MB * 1024 * 1024

app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH

ALLOWED_EXTENSIONS = {
    "pdf", "doc", "docx", "txt",
    "jpg", "jpeg", "png", "webp",
    "xls", "xlsx", "csv",
    "ppt", "pptx"
}

UNIVERSITIES_ZAMBIA = [
    "Copperbelt University (CBU)",
    "University of Zambia (UNZA)",
    "Mulungushi University",
    "Nkrumah University",
    "Mukuba University",
    "Chalimbana University",
    "Kwame Nkrumah University",
    "Kapasa Makasa University",
    "Levy Mwanawasa Medical University",
    "Mulungushi University School of Medicine",
    "Zambia Catholic University",
    "University of Lusaka",
    "Information and Communications University",
    "Lusaka Apex Medical University",
    "Texila American University Zambia",
    "Zambia Open University",
    "Rockview University",
    "Cavendish University Zambia",
    "National Institute of Public Administration",
    "Other University in Zambia"
]

MODES_OF_STUDY = [
    "Full-time",
    "Part-time",
    "Distance Learning",
    "Open and Distance Learning",
    "Online",
    "Evening",
    "Weekend"
]

SERVICE_CATEGORIES = [
    "Result Verification & Certification",
    "TPN Centre",
    "Farmer Registration",
    "Higher Education Applications",
    "Higher Education Materials",
    "Assignments",
    "Supporting Documents",
    "Other Service"
]

STATUSES = [
    "New",
    "Processing",
    "Awaiting Client",
    "Completed",
    "Cancelled"
]


# ============================================================
# BASIC HELPERS
# ============================================================

def utc_now():
    return datetime.now(timezone.utc).isoformat()


def configured():
    return bool(SUPABASE_URL and SUPABASE_SERVICE_KEY)


def supabase_headers(extra=None):
    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
    }
    if extra:
        headers.update(extra)
    return headers


def db_url(table):
    return f"{SUPABASE_URL}/rest/v1/{table}"


def storage_url(path=""):
    base = f"{SUPABASE_URL}/storage/v1"
    return f"{base}/{path.lstrip('/')}"


def db_get(table, params=None):
    if not configured():
        raise RuntimeError("Supabase is not configured.")
    r = requests.get(
        db_url(table),
        headers=supabase_headers({"Accept": "application/json"}),
        params=params or {},
        timeout=30
    )
    if not r.ok:
        raise RuntimeError(f"Database GET failed for {table}: {r.status_code} {r.text[:500]}")
    return r.json()


def db_insert(table, payload, select="*"):
    if not configured():
        raise RuntimeError("Supabase is not configured.")
    r = requests.post(
        db_url(table),
        headers=supabase_headers({
            "Prefer": "return=representation",
            "Accept": "application/json"
        }),
        params={"select": select},
        json=payload,
        timeout=30
    )
    if not r.ok:
        raise RuntimeError(f"Database INSERT failed for {table}: {r.status_code} {r.text[:700]}")
    return r.json()


def db_update(table, filters, payload):
    if not configured():
        raise RuntimeError("Supabase is not configured.")
    r = requests.patch(
        db_url(table),
        headers=supabase_headers({
            "Prefer": "return=representation",
            "Accept": "application/json"
        }),
        params=filters,
        json=payload,
        timeout=30
    )
    if not r.ok:
        raise RuntimeError(f"Database UPDATE failed for {table}: {r.status_code} {r.text[:700]}")
    return r.json()


def db_delete(table, filters):
    if not configured():
        raise RuntimeError("Supabase is not configured.")
    r = requests.delete(
        db_url(table),
        headers=supabase_headers(),
        params=filters,
        timeout=30
    )
    if not r.ok:
        raise RuntimeError(f"Database DELETE failed for {table}: {r.status_code} {r.text[:700]}")
    return True


def first(items):
    return items[0] if items else None


def clean(value):
    return (value or "").strip()


def current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    try:
        return first(db_get("profiles", {
            "id": f"eq.{uid}",
            "select": "*",
            "limit": "1"
        }))
    except Exception:
        return None


def is_admin():
    return session.get("role") == "admin"


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            flash("Please log in first.", "warning")
            return redirect(url_for("login", next=request.path))
        return fn(*args, **kwargs)
    return wrapper


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not is_admin():
            flash("Administrator access is required.", "danger")
            return redirect(url_for("admin_login"))
        return fn(*args, **kwargs)
    return wrapper


def allowed_file(filename):
    if not filename or "." not in filename:
        return False
    return filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def extension(filename):
    return filename.rsplit(".", 1)[1].lower() if "." in filename else ""


def make_reference():
    return "KOJA-" + datetime.now().strftime("%Y%m%d") + "-" + secrets.token_hex(3).upper()


def storage_upload(file_storage, folder, reference):
    if not file_storage or not file_storage.filename:
        return None

    if not allowed_file(file_storage.filename):
        raise ValueError("Unsupported file type.")

    ext = extension(file_storage.filename)
    safe_name = f"{uuid.uuid4().hex}.{ext}"
    path = f"{folder}/{reference}/{safe_name}"

    data = file_storage.read()
    mime = file_storage.mimetype or "application/octet-stream"

    url = storage_url(f"object/{STORAGE_BUCKET}/{path}")
    headers = supabase_headers({
        "Content-Type": mime,
        "x-upsert": "false"
    })

    r = requests.post(url, headers=headers, data=data, timeout=60)

    if not r.ok:
        raise RuntimeError(
            f"Storage upload failed: {r.status_code} {r.text[:700]}"
        )

    return {
        "path": path,
        "original_name": file_storage.filename,
        "mime_type": mime,
        "size": len(data)
    }


def storage_download(path):
    if not path:
        abort(404)

    url = storage_url(f"object/{STORAGE_BUCKET}/{path}")
    r = requests.get(
        url,
        headers=supabase_headers(),
        timeout=60
    )

    if not r.ok:
        abort(404)

    return r.content


def notify(user_id, title, message, request_id=None):
    try:
        db_insert("notifications", {
            "user_id": user_id,
            "title": title,
            "message": message,
            "request_id": request_id,
            "is_read": False,
            "created_at": utc_now()
        })
    except Exception:
        pass


# ============================================================
# HTML
# ============================================================

BASE = """
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{{ title or 'KOJA AFRICA' }}</title>
<style>
:root{
 --primary:#0b5ed7;
 --dark:#10233f;
 --green:#198754;
 --danger:#dc3545;
 --light:#f5f7fb;
 --border:#dce2ea;
}
*{box-sizing:border-box}
body{
 margin:0;
 font-family:Arial,Helvetica,sans-serif;
 background:var(--light);
 color:#172033;
}
nav{
 background:var(--dark);
 color:#fff;
 padding:14px 5%;
 display:flex;
 align-items:center;
 justify-content:space-between;
 gap:15px;
 flex-wrap:wrap;
}
nav a{color:#fff;text-decoration:none;margin:0 6px}
.brand{font-size:21px;font-weight:800}
.container{max-width:1150px;margin:25px auto;padding:0 15px}
.card{
 background:#fff;
 border:1px solid var(--border);
 border-radius:14px;
 padding:20px;
 margin-bottom:18px;
 box-shadow:0 2px 8px rgba(0,0,0,.04)
}
.grid{
 display:grid;
 grid-template-columns:repeat(auto-fit,minmax(240px,1fr));
 gap:15px;
}
input,select,textarea{
 width:100%;
 padding:11px 12px;
 border:1px solid #cbd3df;
 border-radius:9px;
 font-size:15px;
 background:#fff;
}
textarea{min-height:130px;resize:vertical}
label{font-weight:700;font-size:14px;display:block;margin-bottom:6px}
.field{margin-bottom:14px}
button,.btn{
 border:0;
 border-radius:9px;
 padding:11px 16px;
 cursor:pointer;
 text-decoration:none;
 display:inline-block;
 font-weight:700;
 background:var(--primary);
 color:#fff;
}
.btn.green{background:var(--green)}
.btn.dark{background:var(--dark)}
.btn.red{background:var(--danger)}
.btn.gray{background:#6c757d}
.badge{
 display:inline-block;
 padding:5px 9px;
 border-radius:20px;
 background:#e9eef8;
 font-size:12px;
 font-weight:700;
}
.alert{
 padding:12px 14px;
 border-radius:9px;
 margin-bottom:12px;
 background:#e9eef8;
}
.alert.danger{background:#f8d7da}
.alert.success{background:#d1e7dd}
.alert.warning{background:#fff3cd}
table{width:100%;border-collapse:collapse}
th,td{text-align:left;padding:10px;border-bottom:1px solid var(--border);vertical-align:top}
.small{font-size:13px;color:#657085}
.hero{
 padding:40px 20px;
 text-align:center;
 background:linear-gradient(135deg,#10233f,#0b5ed7);
 color:white;
 border-radius:18px;
 margin-bottom:20px;
}
h1,h2,h3{color:var(--dark)}
.hero h1{color:white;font-size:34px;margin:5px}
.actions{display:flex;gap:8px;flex-wrap:wrap}
details summary{cursor:pointer;font-weight:700}
@media(max-width:650px){
 th:nth-child(3),td:nth-child(3){display:none}
 .hero h1{font-size:27px}
}
</style>
</head>
<body>
<nav>
 <div class="brand">KOJA AFRICA</div>
 <div>
 {% if session.get('user_id') %}
   <a href="{{ url_for('dashboard') }}">Dashboard</a>
   <a href="{{ url_for('new_request') }}">Submit Work</a>
   <a href="{{ url_for('notifications') }}">Notifications</a>
   {% if session.get('role') == 'admin' %}
     <a href="{{ url_for('admin_dashboard') }}">Admin</a>
   {% endif %}
   <a href="{{ url_for('logout') }}">Logout</a>
 {% else %}
   <a href="{{ url_for('login') }}">Login</a>
   <a href="{{ url_for('register') }}">Register</a>
 {% endif %}
 </div>
</nav>

<div class="container">
{% with messages=get_flashed_messages(with_categories=true) %}
 {% for category,message in messages %}
   <div class="alert {{ category }}">{{ message }}</div>
 {% endfor %}
{% endwith %}

{{ body|safe }}
</div>
</body>
</html>
"""


def page(title, body):
    return render_template_string(BASE, title=title, body=body)


# ============================================================
# PUBLIC
# ============================================================

@app.route("/")
def home():
    body = """
    <div class="hero">
      <h1>KOJA AFRICA</h1>
      <p>Submit your work. KOJA processes it. Receive the finished document.</p>
      <div class="actions" style="justify-content:center;margin-top:18px">
        <a class="btn green" href="/register">Create Client Account</a>
        <a class="btn" href="/login">Client Login</a>
      </div>
    </div>

    <div class="grid">
      <div class="card"><h3>Higher Education</h3><p>University applications, supporting documents and academic materials.</p></div>
      <div class="card"><h3>Assignments</h3><p>Submit questions and source files for processing and return.</p></div>
      <div class="card"><h3>Verification</h3><p>Result verification and certification-related requests.</p></div>
      <div class="card"><h3>Business & Agriculture</h3><p>TPN Centre, farmer registration and other supported services.</p></div>
    </div>

    <div class="card">
      <h2>How KOJA Works</h2>
      <p><b>1. Submit Request</b> → <b>2. New</b> → <b>3. Processing</b> →
      <b>4. Completed</b> → <b>5. Download Finished File</b></p>
    </div>
    """
    return page("KOJA AFRICA", body)


@app.route("/health")
def health():
    return {
        "status": "ok",
        "app": "KOJA AFRICA",
        "supabase_configured": configured(),
        "time": utc_now()
    }


# ============================================================
# AUTH
# ============================================================

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        full_name = clean(request.form.get("full_name"))
        email = clean(request.form.get("email")).lower()
        phone = clean(request.form.get("phone"))
        password = request.form.get("password", "")

        if not full_name or not email or not phone or len(password) < 6:
            flash("Enter full name, email, contact number and a password of at least 6 characters.", "danger")
            return redirect(url_for("register"))

        try:
            existing = db_get("profiles", {
                "email": f"eq.{email}",
                "select": "id",
                "limit": "1"
            })
            if existing:
                flash("An account with that email already exists.", "warning")
                return redirect(url_for("login"))

            rows = db_insert("profiles", {
                "full_name": full_name,
                "email": email,
                "phone": phone,
                "password_hash": generate_password_hash(password),
                "role": "client",
                "created_at": utc_now()
            })

            user = first(rows)
            session["user_id"] = user["id"]
            session["role"] = "client"
            flash("Account created successfully.", "success")
            return redirect(url_for("dashboard"))

        except Exception as e:
            flash(str(e), "danger")

    body = """
    <div class="card">
      <h2>Create Client Account</h2>
      <form method="post">
        <div class="grid">
          <div class="field"><label>Full Name</label><input name="full_name" required></div>
          <div class="field"><label>Email Address</label><input type="email" name="email" required></div>
          <div class="field"><label>Contact Number</label><input name="phone" placeholder="+260..." required></div>
          <div class="field"><label>Password</label><input type="password" name="password" minlength="6" required></div>
        </div>
        <button>Create Account</button>
      </form>
    </div>
    """
    return page("Register", body)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = clean(request.form.get("email")).lower()
        password = request.form.get("password", "")

        try:
            rows = db_get("profiles", {
                "email": f"eq.{email}",
                "select": "*",
                "limit": "1"
            })
            user = first(rows)

            if not user or not check_password_hash(user.get("password_hash", ""), password):
                flash("Invalid email or password.", "danger")
                return redirect(url_for("login"))

            session.clear()
            session["user_id"] = user["id"]
            session["role"] = user.get("role", "client")
            return redirect(url_for("admin_dashboard" if session["role"] == "admin" else "dashboard"))

        except Exception as e:
            flash(str(e), "danger")

    body = """
    <div class="card" style="max-width:500px;margin:auto">
      <h2>Client Login</h2>
      <form method="post">
        <div class="field"><label>Email</label><input type="email" name="email" required></div>
        <div class="field"><label>Password</label><input type="password" name="password" required></div>
        <button>Login</button>
      </form>
      <p class="small">Need an account? <a href="/register">Register here</a>.</p>
    </div>
    """
    return page("Login", body)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


@app.route("/admin-login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        email = clean(request.form.get("email")).lower()
        password = request.form.get("password", "")

        if email == ADMIN_EMAIL and secrets.compare_digest(password, ADMIN_PASSWORD):
            session.clear()
            session["user_id"] = "ADMIN"
            session["role"] = "admin"
            return redirect(url_for("admin_dashboard"))

        flash("Invalid administrator credentials.", "danger")

    body = """
    <div class="card" style="max-width:500px;margin:auto">
      <h2>KOJA Administrator</h2>
      <form method="post">
        <div class="field"><label>Admin Email</label><input type="email" name="email" required></div>
        <div class="field"><label>Admin Password</label><input type="password" name="password" required></div>
        <button>Administrator Login</button>
      </form>
    </div>
    """
    return page("Admin Login", body)


# ============================================================
# CLIENT DASHBOARD
# ============================================================

@app.route("/dashboard")
@login_required
def dashboard():
    user = current_user()
    if not user:
        session.clear()
        return redirect(url_for("login"))

    try:
        requests_list = db_get("service_requests", {
            "client_id": f"eq.{user['id']}",
            "select": "*",
            "order": "created_at.desc"
        })
    except Exception as e:
        flash(str(e), "danger")
        requests_list = []

    body = f"""
    <div class="hero">
      <h1>Welcome, {user.get('full_name','Client')}</h1>
      <p>KOJA AFRICA client service centre</p>
      <a class="btn green" href="/request/new">Submit New Work</a>
    </div>

    <div class="card">
      <h2>My Requests</h2>
      <p class="small">Track every job from submission to finished-file delivery.</p>
      {render_request_table(requests_list)}
    </div>
    """
    return page("Client Dashboard", body)


def render_request_table(items):
    if not items:
        return "<p>No requests yet. <a href='/request/new'>Submit your first request.</a></p>"

    rows = ""
    for x in items:
        ref = x.get("reference_no", "")
        status = x.get("status", "New")
        rows += f"""
        <tr>
          <td><b>{ref}</b><br><span class="small">{x.get('service_category','')}</span></td>
          <td>{x.get('subject','')}</td>
          <td><span class="badge">{status}</span></td>
          <td>{str(x.get('created_at',''))[:19]}</td>
          <td><a class="btn" href="/request/{x.get('id')}">Open</a></td>
        </tr>
        """

    return f"""
    <div style="overflow:auto">
    <table>
      <thead><tr>
        <th>Reference</th><th>Subject</th><th>Status</th><th>Submitted</th><th></th>
      </tr></thead>
      <tbody>{rows}</tbody>
    </table>
    </div>
    """


# ============================================================
# NEW SERVICE REQUEST
# ============================================================

@app.route("/request/new", methods=["GET", "POST"])
@login_required
def new_request():
    user = current_user()
    if not user:
        return redirect(url_for("login"))

    if request.method == "POST":
        category = clean(request.form.get("service_category"))
        subject = clean(request.form.get("subject"))
        description = clean(request.form.get("description"))

        if not category or not subject:
            flash("Service category and subject are required.", "danger")
            return redirect(url_for("new_request"))

        reference = make_reference()

        # General client information
        full_name = clean(request.form.get("client_full_name")) or user.get("full_name", "")
        email = clean(request.form.get("client_email")) or user.get("email", "")
        phone = clean(request.form.get("client_phone")) or user.get("phone", "")
        address = clean(request.form.get("client_address"))
        gender = clean(request.form.get("gender"))
        date_of_birth = clean(request.form.get("date_of_birth"))
        national_id = clean(request.form.get("national_id"))

        # University / higher education information
        university = clean(request.form.get("university"))
        university_other = clean(request.form.get("university_other"))
        mode_of_study = clean(request.form.get("mode_of_study"))
        school = clean(request.form.get("school"))
        programme = clean(request.form.get("programme"))
        study_level = clean(request.form.get("study_level"))
        student_number = clean(request.form.get("student_number"))
        year_of_study = clean(request.form.get("year_of_study"))
        intake = clean(request.form.get("intake"))

        # Other education/application information
        application_type = clean(request.form.get("application_type"))
        previous_school = clean(request.form.get("previous_school"))
        grade_or_result = clean(request.form.get("grade_or_result"))

        # Agriculture / TPN information
        farmer_name = clean(request.form.get("farmer_name"))
        farm_location = clean(request.form.get("farm_location"))
        farming_type = clean(request.form.get("farming_type"))
        tpn_number = clean(request.form.get("tpn_number"))

        try:
            row = {
                "client_id": user["id"],
                "reference_no": reference,
                "service_category": category,
                "subject": subject,
                "description": description,
                "status": "New",
                "client_full_name": full_name,
                "client_email": email,
                "client_phone": phone,
                "client_address": address,
                "gender": gender,
                "date_of_birth": date_of_birth or None,
                "national_id": national_id,

                "university": university,
                "university_other": university_other,
                "mode_of_study": mode_of_study,
                "school": school,
                "programme": programme,
                "study_level": study_level,
                "student_number": student_number,
                "year_of_study": year_of_study,
                "intake": intake,

                "application_type": application_type,
                "previous_school": previous_school,
                "grade_or_result": grade_or_result,

                "farmer_name": farmer_name,
                "farm_location": farm_location,
                "farming_type": farming_type,
                "tpn_number": tpn_number,

                "created_at": utc_now(),
                "updated_at": utc_now()
            }

            created = db_insert("service_requests", row)
            created_request = first(created)

            uploaded_count = 0
            files = request.files.getlist("supporting_files")

            for f in files:
                if not f or not f.filename:
                    continue

                info = storage_upload(f, "client-files", reference)

                db_insert("request_files", {
                    "request_id": created_request["id"],
                    "client_id": user["id"],
                    "file_name": info["original_name"],
                    "storage_path": info["path"],
                    "mime_type": info["mime_type"],
                    "file_size": info["size"],
                    "file_type": "supporting",
                    "created_at": utc_now()
                })
                uploaded_count += 1

            notify(
                user["id"],
                "Request Submitted",
                f"Your KOJA request {reference} has been submitted and is now New.",
                created_request["id"]
            )

            flash(
                f"Request submitted successfully. Reference: {reference}. Files uploaded: {uploaded_count}.",
                "success"
            )
            return redirect(url_for("view_request", request_id=created_request["id"]))

        except Exception as e:
            flash(str(e), "danger")

    university_options = "".join(
        f"<option>{u}</option>" for u in UNIVERSITIES_ZAMBIA
    )
    mode_options = "".join(
        f"<option>{m}</option>" for m in MODES_OF_STUDY
    )
    service_options = "".join(
        f"<option>{s}</option>" for s in SERVICE_CATEGORIES
    )

    body = f"""
    <div class="card">
      <h2>Submit Work to KOJA AFRICA</h2>
      <p class="small">
        Enter the client's information accurately. For university-related work,
        complete the university, mode of study and school/programme information.
      </p>

      <form method="post" enctype="multipart/form-data">

        <h3>1. Service</h3>
        <div class="grid">
          <div class="field">
            <label>Service Category *</label>
            <select name="service_category" required>{service_options}</select>
          </div>
          <div class="field">
            <label>Subject / Job Title *</label>
            <input name="subject" required placeholder="e.g. University application">
          </div>
        </div>

        <div class="field">
          <label>Describe what you want KOJA to process</label>
          <textarea name="description" placeholder="Give clear instructions, deadlines and other important details."></textarea>
        </div>

        <h3>2. Client Information</h3>
        <div class="grid">
          <div class="field"><label>Full Name</label><input name="client_full_name"></div>
          <div class="field"><label>Email Address</label><input type="email" name="client_email"></div>
          <div class="field"><label>Contact Number</label><input name="client_phone"></div>
          <div class="field"><label>Address / Town</label><input name="client_address"></div>
          <div class="field"><label>Gender</label>
            <select name="gender"><option value="">Select</option><option>Male</option><option>Female</option><option>Other</option></select>
          </div>
          <div class="field"><label>Date of Birth</label><input type="date" name="date_of_birth"></div>
          <div class="field"><label>National ID / NRC</label><input name="national_id"></div>
        </div>

        <h3>3. University / Higher Education</h3>
        <div class="grid">
          <div class="field">
            <label>University in Zambia</label>
            <select name="university">
              <option value="">Select University</option>
              {university_options}
            </select>
          </div>
          <div class="field">
            <label>If Other University</label>
            <input name="university_other" placeholder="Enter university name">
          </div>
          <div class="field">
            <label>Mode of Study</label>
            <select name="mode_of_study">
              <option value="">Select mode</option>
              {mode_options}
            </select>
          </div>
          <div class="field"><label>School / Faculty</label><input name="school" placeholder="e.g. School of Natural Sciences"></div>
          <div class="field"><label>Programme / Course</label><input name="programme"></div>
          <div class="field">
            <label>Study Level</label>
            <select name="study_level">
              <option value="">Select</option>
              <option>Certificate</option><option>Diploma</option><option>Bachelor's Degree</option>
              <option>Postgraduate Diploma</option><option>Master's Degree</option><option>PhD</option>
              <option>Other</option>
            </select>
          </div>
          <div class="field"><label>Student Number</label><input name="student_number"></div>
          <div class="field"><label>Year of Study</label><input name="year_of_study" placeholder="e.g. Year 2"></div>
          <div class="field"><label>Intake</label><input name="intake" placeholder="e.g. January 2027"></div>
        </div>

        <h3>4. Application / Academic Details</h3>
        <div class="grid">
          <div class="field"><label>Application Type</label><input name="application_type" placeholder="e.g. undergraduate admission"></div>
          <div class="field"><label>Previous School / College</label><input name="previous_school"></div>
          <div class="field"><label>Grades / Results</label><input name="grade_or_result"></div>
        </div>

        <h3>5. Farmer / TPN Information</h3>
        <div class="grid">
          <div class="field"><label>Farmer Name</label><input name="farmer_name"></div>
          <div class="field"><label>Farm Location</label><input name="farm_location"></div>
          <div class="field"><label>Farming Type</label><input name="farming_type" placeholder="e.g. crop/livestock"></div>
          <div class="field"><label>TPN Number</label><input name="tpn_number"></div>
        </div>

        <h3>6. Supporting Documents</h3>
        <div class="field">
          <label>Upload documents</label>
          <input type="file" name="supporting_files" multiple
            accept=".pdf,.doc,.docx,.txt,.jpg,.jpeg,.png,.webp,.xls,.xlsx,.csv,.ppt,.pptx">
          <p class="small">Allowed: PDF, Word, Excel, PowerPoint, images and text files. Maximum total request upload size: {MAX_FILE_MB} MB.</p>
        </div>

        <button class="btn green">Submit Request to KOJA</button>
      </form>
    </div>
    """
    return page("Submit Work", body)


# ============================================================
# VIEW CLIENT REQUEST
# ============================================================

@app.route("/request/<request_id>")
@login_required
def view_request(request_id):
    try:
        rows = db_get("service_requests", {
            "id": f"eq.{request_id}",
            "select": "*",
            "limit": "1"
        })
        req = first(rows)

        if not req:
            abort(404)

        if not is_admin() and req.get("client_id") != session.get("user_id"):
            abort(403)

        files = db_get("request_files", {
            "request_id": f"eq.{request_id}",
            "select": "*",
            "order": "created_at.asc"
        })

        messages = db_get("request_messages", {
            "request_id": f"eq.{request_id}",
            "select": "*",
            "order": "created_at.asc"
        })

        file_rows = ""
        for f in files:
            file_rows += f"""
            <tr>
              <td>{f.get('file_name','')}</td>
              <td>{f.get('file_type','')}</td>
              <td>
                <a class="btn" href="/file/{f.get('id')}">Download</a>
              </td>
            </tr>
            """

        msg_rows = ""
        for m in messages:
            sender = m.get("sender_role", "client")
            msg_rows += f"""
            <div class="card">
              <b>{sender.title()}</b>
              <div>{m.get('message','')}</div>
              <div class="small">{str(m.get('created_at',''))[:19]}</div>
            </div>
            """

        university = req.get("university") or req.get("university_other") or ""
        body = f"""
        <div class="card">
          <h2>{req.get('reference_no')}</h2>
          <span class="badge">{req.get('status','New')}</span>
          <h3>{req.get('subject','')}</h3>
          <p>{req.get('description','')}</p>
        </div>

        <div class="grid">
          <div class="card">
            <h3>Client</h3>
            <p><b>Name:</b> {req.get('client_full_name','')}</p>
            <p><b>Email:</b> {req.get('client_email','')}</p>
            <p><b>Contact:</b> {req.get('client_phone','')}</p>
            <p><b>Address:</b> {req.get('client_address','')}</p>
          </div>

          <div class="card">
            <h3>University</h3>
            <p><b>University:</b> {university}</p>
            <p><b>Mode:</b> {req.get('mode_of_study','')}</p>
            <p><b>School:</b> {req.get('school','')}</p>
            <p><b>Programme:</b> {req.get('programme','')}</p>
            <p><b>Level:</b> {req.get('study_level','')}</p>
            <p><b>Student No.:</b> {req.get('student_number','')}</p>
          </div>
        </div>

        <div class="card">
          <h3>Files</h3>
          <div style="overflow:auto">
          <table>
            <tr><th>File</th><th>Type</th><th></th></tr>
            {file_rows or '<tr><td colspan="3">No files.</td></tr>'}
          </table>
          </div>
        </div>

        <div class="card">
          <h3>Messages</h3>
          {msg_rows or '<p>No messages yet.</p>'}
        </div>
        """

        if is_admin():
            body += f"""
            <div class="card">
              <h3>Admin Processing</h3>

              <form method="post" action="/admin/request/{request_id}/status">
                <div class="field">
                  <label>Status</label>
                  <select name="status">
                    {''.join(f'<option {"selected" if s == req.get("status") else ""}>{s}</option>' for s in STATUSES)}
                  </select>
                </div>
                <button>Update Status</button>
              </form>

              <hr>

              <form method="post" action="/admin/request/{request_id}/message">
                <div class="field">
                  <label>Send Message to Client</label>
                  <textarea name="message" required placeholder="Tell the client what is happening or what is required."></textarea>
                </div>
                <button class="btn dark">Send Message</button>
              </form>

              <hr>

              <form method="post" action="/admin/request/{request_id}/complete"
                    enctype="multipart/form-data">
                <h3>Return Finished Work</h3>
                <div class="field">
                  <label>Finished PDF / Word / Excel / PowerPoint / other supported document</label>
                  <input type="file" name="finished_file" required>
                </div>
                <div class="field">
                  <label>Completion Message</label>
                  <textarea name="completion_message" placeholder="Your work is ready for download."></textarea>
                </div>
                <button class="btn green">Upload Finished File & Complete</button>
              </form>
            </div>
            """

        return page(req.get("reference_no", "Request"), body)

    except Exception as e:
        flash(str(e), "danger")
        return redirect(url_for("dashboard"))


# ============================================================
# FILE DOWNLOAD
# ============================================================

@app.route("/file/<file_id>")
@login_required
def download_file(file_id):
    try:
        rows = db_get("request_files", {
            "id": f"eq.{file_id}",
            "select": "*",
            "limit": "1"
        })
        f = first(rows)

        if not f:
            abort(404)

        req_rows = db_get("service_requests", {
            "id": f"eq.{f['request_id']}",
            "select": "client_id,reference_no,status",
            "limit": "1"
        })
        req = first(req_rows)

        if not req:
            abort(404)

        if not is_admin() and req.get("client_id") != session.get("user_id"):
            abort(403)

        # Clients can download supporting files and completed files.
        data = storage_download(f.get("storage_path"))

        return send_file(
            io.BytesIO(data),
            as_attachment=True,
            download_name=f.get("file_name", "KOJA-file"),
            mimetype=f.get("mime_type") or "application/octet-stream"
        )

    except Exception:
        abort(404)


# ============================================================
# ADMIN DASHBOARD
# ============================================================

@app.route("/admin")
@admin_required
def admin_dashboard():
    try:
        all_requests = db_get("service_requests", {
            "select": "*",
            "order": "created_at.desc"
        })
        clients = db_get("profiles", {
            "role": "eq.client",
            "select": "id,full_name,email,phone,created_at",
            "order": "created_at.desc"
        })
    except Exception as e:
        flash(str(e), "danger")
        all_requests = []
        clients = []

    counts = {}
    for s in STATUSES:
        counts[s] = sum(1 for r in all_requests if r.get("status") == s)

    stats = "".join(
        f'<div class="card"><h3>{s}</h3><div style="font-size:28px;font-weight:800">{counts[s]}</div></div>'
        for s in STATUSES
    )

    body = f"""
    <div class="hero">
      <h1>KOJA AFRICA ADMIN</h1>
      <p>Manage client requests, process work and return finished files.</p>
    </div>

    <div class="grid">{stats}</div>

    <div class="card">
      <h2>Service Requests</h2>
      {render_admin_table(all_requests)}
    </div>

    <div class="card">
      <h2>Clients</h2>
      <div style="overflow:auto">
      <table>
        <tr><th>Name</th><th>Email</th><th>Contact</th><th>Registered</th></tr>
        {''.join(
          f"<tr><td>{c.get('full_name','')}</td><td>{c.get('email','')}</td>"
          f"<td>{c.get('phone','')}</td><td>{str(c.get('created_at',''))[:19]}</td></tr>"
          for c in clients
        ) or '<tr><td colspan="4">No clients.</td></tr>'}
      </table>
      </div>
    </div>
    """
    return page("Admin Dashboard", body)


def render_admin_table(items):
    if not items:
        return "<p>No service requests.</p>"

    rows = ""
    for x in items:
        rows += f"""
        <tr>
          <td><b>{x.get('reference_no','')}</b></td>
          <td>{x.get('client_full_name','')}</td>
          <td>{x.get('service_category','')}</td>
          <td>{x.get('subject','')}</td>
          <td><span class="badge">{x.get('status','New')}</span></td>
          <td>{str(x.get('created_at',''))[:19]}</td>
          <td><a class="btn" href="/request/{x.get('id')}">Process</a></td>
        </tr>
        """

    return f"""
    <div style="overflow:auto">
    <table>
      <tr>
        <th>Reference</th><th>Client</th><th>Service</th>
        <th>Subject</th><th>Status</th><th>Date</th><th></th>
      </tr>
      {rows}
    </table>
    </div>
    """


# ============================================================
# ADMIN PROCESSING
# ============================================================

@app.route("/admin/request/<request_id>/status", methods=["POST"])
@admin_required
def admin_status(request_id):
    status = clean(request.form.get("status"))

    if status not in STATUSES:
        flash("Invalid status.", "danger")
        return redirect(url_for("view_request", request_id=request_id))

    try:
        rows = db_get("service_requests", {
            "id": f"eq.{request_id}",
            "select": "id,client_id,reference_no",
            "limit": "1"
        })
        req = first(rows)
        if not req:
            abort(404)

        db_update(
            "service_requests",
            {"id": f"eq.{request_id}"},
            {"status": status, "updated_at": utc_now()}
        )

        notify(
            req["client_id"],
            f"Request {status}",
            f"Your request {req['reference_no']} is now {status}.",
            request_id
        )

        flash("Status updated.", "success")

    except Exception as e:
        flash(str(e), "danger")

    return redirect(url_for("view_request", request_id=request_id))


@app.route("/admin/request/<request_id>/message", methods=["POST"])
@admin_required
def admin_message(request_id):
    message = clean(request.form.get("message"))

    if not message:
        flash("Message cannot be empty.", "danger")
        return redirect(url_for("view_request", request_id=request_id))

    try:
        req = first(db_get("service_requests", {
            "id": f"eq.{request_id}",
            "select": "id,client_id,reference_no",
            "limit": "1"
        }))

        if not req:
            abort(404)

        db_insert("request_messages", {
            "request_id": request_id,
            "sender_role": "admin",
            "sender_id": "ADMIN",
            "message": message,
            "created_at": utc_now()
        })

        notify(
            req["client_id"],
            "New KOJA Message",
            f"You have a new message concerning {req['reference_no']}.",
            request_id
        )

        flash("Message sent to client.", "success")

    except Exception as e:
        flash(str(e), "danger")

    return redirect(url_for("view_request", request_id=request_id))


@app.route("/admin/request/<request_id>/complete", methods=["POST"])
@admin_required
def admin_complete(request_id):
    finished = request.files.get("finished_file")
    completion_message = clean(request.form.get("completion_message"))

    if not finished or not finished.filename:
        flash("Select the finished file.", "danger")
        return redirect(url_for("view_request", request_id=request_id))

    try:
        req = first(db_get("service_requests", {
            "id": f"eq.{request_id}",
            "select": "id,client_id,reference_no",
            "limit": "1"
        }))

        if not req:
            abort(404)

        info = storage_upload(finished, "completed-files", req["reference_no"])

        db_insert("request_files", {
            "request_id": request_id,
            "client_id": req["client_id"],
            "file_name": info["original_name"],
            "storage_path": info["path"],
            "mime_type": info["mime_type"],
            "file_size": info["size"],
            "file_type": "completed",
            "created_at": utc_now()
        })

        db_update(
            "service_requests",
            {"id": f"eq.{request_id}"},
            {
                "status": "Completed",
                "completion_message": completion_message,
                "completed_at": utc_now(),
                "updated_at": utc_now()
            }
        )

        final_message = completion_message or (
            f"Your KOJA work {req['reference_no']} is completed. "
            "The finished file is now available in your request."
        )

        db_insert("request_messages", {
            "request_id": request_id,
            "sender_role": "admin",
            "sender_id": "ADMIN",
            "message": final_message,
            "created_at": utc_now()
        })

        notify(
            req["client_id"],
            "Work Completed",
            final_message,
            request_id
        )

        flash("Finished file uploaded. Request marked Completed.", "success")

    except Exception as e:
        flash(str(e), "danger")

    return redirect(url_for("view_request", request_id=request_id))


# ============================================================
# NOTIFICATIONS
# ============================================================

@app.route("/notifications")
@login_required
def notifications():
    if is_admin():
        return redirect(url_for("admin_dashboard"))

    try:
        items = db_get("notifications", {
            "user_id": f"eq.{session['user_id']}",
            "select": "*",
            "order": "created_at.desc"
        })
    except Exception as e:
        flash(str(e), "danger")
        items = []

    rows = ""
    for n in items:
        rows += f"""
        <div class="card">
          <h3>{n.get('title','')}</h3>
          <p>{n.get('message','')}</p>
          <div class="small">{str(n.get('created_at',''))[:19]}</div>
        </div>
        """

    body = f"""
    <h2>Notifications</h2>
    {rows or '<div class="card">No notifications.</div>'}
    """
    return page("Notifications", body)


# ============================================================
# 404 / 413 / ERRORS
# ============================================================

@app.errorhandler(404)
def not_found(e):
    return page(
        "Not Found",
        "<div class='card'><h2>Page not found</h2><p>The requested page does not exist.</p><a class='btn' href='/'>Home</a></div>"
    ), 404


@app.errorhandler(403)
def forbidden(e):
    return page(
        "Forbidden",
        "<div class='card'><h2>Access denied</h2><p>You do not have permission to access this request.</p></div>"
    ), 403


@app.errorhandler(413)
def too_large(e):
    return page(
        "File Too Large",
        f"<div class='card'><h2>Upload too large</h2><p>The maximum upload size is {MAX_FILE_MB} MB.</p></div>"
    ), 413


@app.errorhandler(Exception)
def unexpected(e):
    # Keep production errors away from the client while still giving
    # a useful message for configuration/database failures.
    return page(
        "KOJA Error",
        f"<div class='card'><h2>Something went wrong</h2><p>{str(e)}</p><a class='btn' href='/'>Home</a></div>"
    ), 500


# ============================================================
# LOCAL ENTRY POINT
# ============================================================

if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)

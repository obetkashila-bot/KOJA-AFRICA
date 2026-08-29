
import os
import io
import json
import uuid
import sqlite3
import secrets
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path

from flask import (
    Flask,
    request,
    redirect,
    url_for,
    session,
    render_template_string,
    flash,
    get_flashed_messages,
    send_from_directory,
    abort,
)

from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
# ============================================================
# KOJA AFRICA
# ============================================================
#
# FIVE SERVICES
# 1. Farmer Registration
# 2. TPIN Services
# 3. University Requests
# 4. Assignment / Question Request
# 5. Other Services
#
# DATABASE:
# Supabase PostgreSQL REST API
#
# STORAGE:
# Supabase Storage
#
# RENDER START:
# gunicorn app:app
# ============================================================


# ============================================================
# CONFIGURATION
# ============================================================

app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    secrets.token_hex(32)
)

app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("koja")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

STORAGE_BUCKET = os.environ.get(
    "SUPABASE_STORAGE_BUCKET",
    "koja-files"
)

ADMIN_EMAIL = os.environ.get(
    "ADMIN_EMAIL",
    "admin@koja-africa.com"
).strip().lower()

ADMIN_PASSWORD = os.environ.get(
    "ADMIN_PASSWORD",
    "CHANGE-THIS-PASSWORD"
)

if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
    logger.warning(
        "SUPABASE_URL or SUPABASE_SERVICE_KEY is missing."
    )


# ============================================================
# CONSTANTS
# ============================================================

PROVINCES = [
    "Central",
    "Copperbelt",
    "Eastern",
    "Luapula",
    "Lusaka",
    "Muchinga",
    "Northern",
    "North-Western",
    "Southern",
    "Western",
]

GENDERS = [
    "Male",
    "Female",
    "Other",
]

BANKS = [
    "ABSA Bank Zambia",
    "Access Bank Zambia",
    "Atlas Mara",
    "Bank of China Zambia",
    "First Capital Bank",
    "First National Bank Zambia",
    "Indo Zambia Bank",
    "Stanbic Bank Zambia",
    "Standard Chartered Bank Zambia",
    "United Bank for Africa Zambia",
    "Zanaco",
]

MOBILE_PROVIDERS = [
    "Airtel Money",
    "MTN MoMo",
    "Zamtel Kwacha",
]

ALLOWED_CLIENT_EXTENSIONS = {
    "pdf",
    "doc",
    "docx",
    "xls",
    "xlsx",
    "jpg",
    "jpeg",
    "png",
    "webp",
}

ALLOWED_RESULT_EXTENSIONS = {
    "pdf",
    "doc",
    "docx",
    "xls",
    "xlsx",
    "jpg",
    "jpeg",
    "png",
    "webp",
}

STATUSES = [
    "Request Received",
    "Processing",
    "Completed",
    "Rejected",
]

SERVICE_LIST = [
    (
        "farmer",
        "Farmer Registration",
        "Complete the three-step farmer registration process."
    ),
    (
        "tpin",
        "TPIN Services",
        "Submit your TPIN-related request."
    ),
    (
        "university",
        "University Request",
        "Submit a university-related request."
    ),
    (
        "assignment",
        "Assignment / Question",
        "Ask a question or upload an assignment and receive an answer."
    ),
    (
        "other",
        "Other Services",
        "Submit another request to KOJA AFRICA."
    ),
]


# ============================================================
# SUPABASE REST
# ============================================================

def supabase_headers(prefer=None):
    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
    }

    if prefer:
        headers["Prefer"] = prefer

    return headers


def db_select(
    table,
    params=None,
    single=False,
):
    url = f"{SUPABASE_URL}/rest/v1/{table}"

    response = requests.get(
        url,
        headers=supabase_headers(),
        params=params or {},
        timeout=30,
    )

    if not response.ok:
        logger.error(
            "Supabase GET %s: %s",
            table,
            response.text
        )
        raise RuntimeError(
            f"Database GET failed for {table}: "
            f"{response.text}"
        )

    data = response.json()

    if single:
        return data[0] if data else None

    return data


def db_insert(
    table,
    data,
    returning=True,
):
    url = f"{SUPABASE_URL}/rest/v1/{table}"

    headers = supabase_headers(
        "return=representation" if returning else "return=minimal"
    )

    response = requests.post(
        url,
        headers=headers,
        json=data,
        timeout=30,
    )

    if not response.ok:
        logger.error(
            "Supabase POST %s: %s",
            table,
            response.text
        )
        raise RuntimeError(
            f"Database INSERT failed for {table}: "
            f"{response.text}"
        )

    if returning:
        return response.json()

    return []


def db_update(
    table,
    params,
    data,
):
    url = f"{SUPABASE_URL}/rest/v1/{table}"

    headers = supabase_headers(
        "return=representation"
    )

    response = requests.patch(
        url,
        headers=headers,
        params=params,
        json=data,
        timeout=30,
    )

    if not response.ok:
        logger.error(
            "Supabase PATCH %s: %s",
            table,
            response.text
        )
        raise RuntimeError(
            f"Database UPDATE failed for {table}: "
            f"{response.text}"
        )

    return response.json()


def db_delete(table, params):
    url = f"{SUPABASE_URL}/rest/v1/{table}"

    response = requests.delete(
        url,
        headers=supabase_headers(),
        params=params,
        timeout=30,
    )

    if not response.ok:
        raise RuntimeError(
            f"Database DELETE failed for {table}: "
            f"{response.text}"
        )

    return True


# ============================================================
# STORAGE
# ============================================================

def storage_upload(
    file_storage,
    folder="uploads",
):
    if not file_storage:
        return None

    original_name = secure_filename(
        file_storage.filename or ""
    )

    if not original_name:
        raise ValueError("Invalid filename.")

    if "." not in original_name:
        raise ValueError("File must have an extension.")

    extension = original_name.rsplit(
        ".",
        1
    )[1].lower()

    if extension not in ALLOWED_CLIENT_EXTENSIONS:
        raise ValueError(
            "Unsupported file type."
        )

    unique_name = (
        f"{folder}/"
        f"{uuid.uuid4().hex}."
        f"{extension}"
    )

    content = file_storage.read()

    if len(content) > 10 * 1024 * 1024:
        raise ValueError(
            "Maximum file size is 10 MB."
        )

    content_type = (
        file_storage.mimetype
        or "application/octet-stream"
    )

    url = (
        f"{SUPABASE_URL}/storage/v1/object/"
        f"{STORAGE_BUCKET}/{unique_name}"
    )

    headers = {
        "Authorization":
            f"Bearer {SUPABASE_SERVICE_KEY}",
        "apikey":
            SUPABASE_SERVICE_KEY,
        "Content-Type":
            content_type,
        "x-upsert":
            "false",
    }

    response = requests.post(
        url,
        headers=headers,
        data=content,
        timeout=60,
    )

    if not response.ok:
        logger.error(
            "Storage upload failed: %s",
            response.text
        )
        raise RuntimeError(
            f"Storage upload failed: {response.text}"
        )

    return {
        "path": unique_name,
        "original_name": original_name,
        "extension": extension,
        "mime_type": content_type,
        "size": len(content),
    }


def storage_download(path):
    url = (
        f"{SUPABASE_URL}/storage/v1/object/"
        f"{STORAGE_BUCKET}/{path}"
    )

    response = requests.get(
        url,
        headers={
            "Authorization":
                f"Bearer {SUPABASE_SERVICE_KEY}",
            "apikey":
                SUPABASE_SERVICE_KEY,
        },
        timeout=60,
    )

    if not response.ok:
        raise RuntimeError(
            "Unable to download file from storage."
        )

    return response.content


# ============================================================
# HELPERS
# ============================================================

def now_iso():
    return datetime.now(timezone.utc).isoformat()


def service_name(service_type):
    for key, name, description in SERVICE_LIST:
        if key == service_type:
            return name

    return "KOJA Service"


def new_request_no():
    stamp = datetime.now(
        timezone.utc
    ).strftime("%Y%m%d")

    return (
        f"KOJA-{stamp}-"
        f"{secrets.token_hex(4).upper()}"
    )


def allowed_file(filename):
    if not filename or "." not in filename:
        return False

    extension = filename.rsplit(
        ".",
        1
    )[1].lower()

    return extension in ALLOWED_CLIENT_EXTENSIONS


def clean_required(name, label=None):
    value = request.form.get(
        name,
        ""
    ).strip()

    if not value:
        raise ValueError(
            f"{label or name.replace('_', ' ').title()} "
            f"is required."
        )

    return value


def current_user():
    user_id = session.get("user_id")

    if not user_id:
        return None

    rows = db_select(
        "profiles",
        {
            "id": f"eq.{user_id}",
            "select": "*",
            "limit": "1",
        }
    )

    return rows[0] if rows else None


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            flash(
                "Please log in first.",
                "error"
            )
            return redirect(
                url_for("login")
            )

        return view(*args, **kwargs)

    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get(
            "admin_logged_in"
        ):
            return redirect(
                url_for("admin_login")
            )

        return view(*args, **kwargs)

    return wrapped


def get_request(request_id):
    rows = db_select(
        "service_requests",
        {
            "id": f"eq.{request_id}",
            "select": "*",
            "limit": "1",
        }
    )

    return rows[0] if rows else None


def get_request_files(request_id):
    return db_select(
        "request_files",
        {
            "request_id":
                f"eq.{request_id}",
            "select": "*",
            "order":
                "created_at.desc",
        }
    )


def add_notification(
    user_id,
    title,
    message,
):
    db_insert(
        "notifications",
        {
            "user_id": user_id,
            "title": title,
            "message": message,
            "is_read": False,
            "created_at": now_iso(),
        },
        returning=False,
    )


def create_request(
    user_id,
    service_type,
    data,
):
    request_no = new_request_no()

    rows = db_insert(
        "service_requests",
        {
            "request_no":
                request_no,
            "user_id":
                user_id,
            "service_type":
                service_type,
            "service_name":
                service_name(service_type),
            "status":
                "Request Received",
            "data_json":
                data,
            "admin_response":
                None,
            "result_file_path":
                None,
            "result_file_name":
                None,
            "created_at":
                now_iso(),
            "updated_at":
                now_iso(),
        }
    )

    if not rows:
        raise RuntimeError(
            "Request was not created."
        )

    request_id = rows[0]["id"]

    add_notification(
        user_id,
        "Request Received",
        (
            f"Your {service_name(service_type)} "
            f"request {request_no} has been received."
        ),
    )

    return request_id, request_no


def attach_file(
    request_id,
    upload,
    category="client",
):
    if not upload:
        return None

    folder = (
        f"requests/{request_id}/"
        f"{category}"
    )

    info = storage_upload(
        upload,
        folder=folder
    )

    db_insert(
        "request_files",
        {
            "request_id":
                request_id,
            "original_name":
                info["original_name"],
            "storage_path":
                info["path"],
            "mime_type":
                info["mime_type"],
            "file_extension":
                info["extension"],
            "file_size":
                info["size"],
            "category":
                category,
            "created_at":
                now_iso(),
        },
        returning=False,
    )

    return info


# ============================================================
# HTML
# ============================================================

CSS = """
<style>
:root{
 --blue:#214f91;
 --blue2:#173d73;
 --green:#19733f;
 --green2:#238b52;
 --ink:#172235;
 --muted:#667085;
 --bg:#f4f7fb;
 --card:#fff;
 --line:#dfe5ec;
 --danger:#c73636;
 --warning:#9a6800;
}
*{box-sizing:border-box}
body{
 margin:0;
 background:var(--bg);
 color:var(--ink);
 font-family:Arial,Helvetica,sans-serif;
}
a{
 text-decoration:none;
 color:inherit
}
.nav{
 background:#fff;
 border-bottom:1px solid var(--line);
 position:sticky;
 top:0;
 z-index:100
}
.nav-inner{
 max-width:1150px;
 margin:auto;
 padding:16px 20px;
 display:flex;
 align-items:center;
 justify-content:space-between;
 gap:20px
}
.logo{
 color:var(--blue);
 font-size:27px;
 font-weight:900
}
.navlinks{
 display:flex;
 flex-wrap:wrap;
 gap:7px
}
.navlinks a{
 padding:9px 12px;
 border-radius:9px;
 font-size:14px
}
.navlinks a:hover{
 background:#eef4fb
}
.container{
 max-width:1150px;
 margin:auto;
 padding:30px 18px 60px
}
.hero{
 background:linear-gradient(
 135deg,
 #eef5ff,
 #fff
 );
 border:1px solid #dce8f8;
 border-radius:24px;
 padding:40px 30px;
 margin-bottom:22px
}
.hero h1{
 color:var(--blue);
 font-size:40px;
 margin:0 0 10px
}
.hero p{
 color:var(--muted);
 font-size:18px;
 line-height:1.6
}
.card{
 background:#fff;
 border:1px solid var(--line);
 border-radius:20px;
 padding:25px;
 margin-bottom:20px;
 box-shadow:0 5px 18px rgba(25,45,70,.05)
}
.card h2{
 margin-top:0
}
.grid{
 display:grid;
 grid-template-columns:
 repeat(2,minmax(0,1fr));
 gap:17px
}
.grid3{
 display:grid;
 grid-template-columns:
 repeat(3,minmax(0,1fr));
 gap:17px
}
.field{
 margin-bottom:17px
}
label{
 display:block;
 font-weight:700;
 margin-bottom:7px
}
input,select,textarea{
 width:100%;
 padding:13px 14px;
 border:1px solid #ccd5e1;
 border-radius:10px;
 font-size:16px;
 background:#fff;
 color:var(--ink)
}
textarea{
 min-height:130px;
 resize:vertical
}
.btn{
 display:inline-block;
 border:0;
 cursor:pointer;
 padding:12px 17px;
 border-radius:10px;
 font-weight:700;
 font-size:15px;
 background:var(--blue);
 color:#fff
}
.btn.green{
 background:var(--green)
}
.btn.light{
 background:#edf3fa;
 color:var(--blue)
}
.btn.danger{
 background:var(--danger)
}
.actions{
 display:flex;
 gap:10px;
 flex-wrap:wrap;
 margin-top:17px
}
.service{
 background:#fff;
 border:1px solid var(--line);
 border-radius:17px;
 padding:21px
}
.service h3{
 margin-top:0
}
.service p{
 color:var(--muted);
 line-height:1.5
}
.stepbar{
 display:flex;
 justify-content:center;
 gap:11px;
 margin:15px 0 27px
}
.step{
 width:44px;
 height:44px;
 border-radius:50%;
 background:#e3e8ef;
 display:flex;
 align-items:center;
 justify-content:center;
 font-weight:800
}
.step.active,.step.done{
 background:var(--green);
 color:#fff
}
.alert{
 border-radius:11px;
 padding:13px 15px;
 margin-bottom:17px
}
.alert.success{
 background:#e6f6ed;
 color:#146437
}
.alert.error{
 background:#fdecec;
 color:#a22626
}
.alert.info{
 background:#eaf2fc;
 color:#24508e
}
.status{
 display:inline-block;
 padding:7px 11px;
 border-radius:999px;
 font-size:13px;
 font-weight:800
}
.status.received{
 background:#e8f1fc;
 color:#24508e
}
.status.processing{
 background:#fff3d5;
 color:#765300
}
.status.completed{
 background:#e4f6eb;
 color:#176d3d
}
.status.rejected{
 background:#fde8e8;
 color:#9e2525
}
.data-table{
 width:100%;
 border-collapse:collapse
}
.data-table th,
.data-table td{
 padding:11px 9px;
 border-bottom:1px solid var(--line);
 text-align:left;
 vertical-align:top
}
.data-table th{
 color:var(--muted);
 font-size:13px
}
.kv{
 display:grid;
 grid-template-columns:220px 1fr
}
.kv div{
 padding:10px 0;
 border-bottom:1px solid #edf0f4
}
.kv .k{
 font-weight:700;
 color:#405067
}
.filebox{
 background:#f7f9fc;
 border:1px dashed #cbd5e1;
 padding:16px;
 border-radius:12px
}
.small{
 color:var(--muted);
 font-size:13px
}
.footer{
 text-align:center;
 padding:35px 20px;
 color:#7c8796
}
.admin-top{
 background:#12263f;
 color:white;
 padding:15px 20px
}
.admin-inner{
 max-width:1150px;
 margin:auto;
 display:flex;
 justify-content:space-between;
 align-items:center
}
.admin-link{
 color:#fff
}
.answer-box{
 background:#f7fafc;
 border-left:4px solid var(--green);
 padding:18px;
 border-radius:10px;
 white-space:pre-wrap;
 line-height:1.6
}
.big-number{
 font-size:32px;
 font-weight:900;
 margin-top:8px
}
@media(max-width:760px){
 .nav-inner{
  flex-direction:column;
  align-items:flex-start
 }
 .grid,.grid3{
  grid-template-columns:1fr
 }
 .hero h1{
  font-size:30px
 }
 .container{
  padding:20px 13px 45px
 }
 .kv{
  grid-template-columns:1fr
 }
 .data-table{
  display:block;
  overflow-x:auto
 }
}
</style>
"""


def page(
    title,
    body,
    admin=False,
):
    user = current_user()

    if admin:
        nav = """
        <div class="admin-top">
          <div class="admin-inner">
            <strong>KOJA AFRICA — ADMIN</strong>
            <a class="admin-link"
               href="/admin/logout">
               Logout
            </a>
          </div>
        </div>
        """
    else:
        if user:
            links = [
                (
                    "Dashboard",
                    url_for("dashboard")
                ),
                (
                    "Services",
                    url_for("services")
                ),
                (
                    "My Requests",
                    url_for("my_requests")
                ),
                (
                    "Notifications",
                    url_for("notifications")
                ),
                (
                    "Profile",
                    url_for("profile")
                ),
                (
                    "Logout",
                    url_for("logout")
                ),
            ]
        else:
            links = [
                (
                    "Home",
                    url_for("home")
                ),
                (
                    "Login",
                    url_for("login")
                ),
                (
                    "Create Account",
                    url_for("register")
                ),
            ]

        nav_links = ""

        for name, link in links:
            nav_links += (
                f'<a href="{link}">'
                f'{name}</a>'
            )

        nav = f"""
        <nav class="nav">
          <div class="nav-inner">
            <a class="logo"
               href="{url_for('dashboard' if user else 'home')}">
               KOJA AFRICA
            </a>
            <div class="navlinks">
              {nav_links}
            </div>
          </div>
        </nav>
        """

    flashes = ""

    for category, message in get_flashed_messages(
        with_categories=True
    ):
        flashes += (
            f'<div class="alert {category}">'
            f'{message}</div>'
        )

    return f"""
    <!doctype html>
    <html lang="en">
    <head>
      <meta charset="utf-8">
      <meta name="viewport"
            content="width=device-width, initial-scale=1">
      <title>{title} | KOJA AFRICA</title>
      {CSS}
    </head>
    <body>
      {nav}

      <main class="container">
        {flashes}
        {body}
      </main>

      <footer class="footer">
        <strong>KOJA AFRICA</strong><br>
        Your Request • KOJA Handles It • You Receive the Result
      </footer>
    </body>
    </html>
    """


# ============================================================
# HOME
# ============================================================

@app.route("/")
def home():
    body = """
    <section class="hero">
      <h1>KOJA AFRICA</h1>

      <p>
        A single platform for service requests,
        academic assignments, questions and document
        processing.
      </p>

      <div class="actions">
        <a class="btn green"
           href="/register">
           Create Account
        </a>

        <a class="btn light"
           href="/login">
           Client Login
        </a>
      </div>
    </section>

    <section class="card">
      <h2>Our Services</h2>

      <div class="grid3">

        <div class="service">
          <h3>Farmer Registration</h3>
          <p>
            Three-step farmer registration,
            location and payment information.
          </p>
        </div>

        <div class="service">
          <h3>TPIN Services</h3>
          <p>
            Submit TPIN-related information
            and supporting documents.
          </p>
        </div>

        <div class="service">
          <h3>University Requests</h3>
          <p>
            Submit university and student
            related requests.
          </p>
        </div>

        <div class="service">
          <h3>Assignment / Questions</h3>
          <p>
            Ask academic questions or upload
            assignments for processing.
          </p>
        </div>

        <div class="service">
          <h3>Other Services</h3>
          <p>
            Submit any other service request
            that KOJA can process.
          </p>
        </div>

      </div>
    </section>
    """

    return page(
        "Home",
        body
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

        full_name = request.form.get(
            "full_name",
            ""
        ).strip()

        email = request.form.get(
            "email",
            ""
        ).strip().lower()

        phone = request.form.get(
            "phone",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        )

        confirm = request.form.get(
            "confirm_password",
            ""
        )

        if not full_name or not email or not password:
            flash(
                "Name, email and password are required.",
                "error"
            )

        elif password != confirm:
            flash(
                "Passwords do not match.",
                "error"
            )

        elif len(password) < 6:
            flash(
                "Password must contain at least 6 characters.",
                "error"
            )

        else:
            try:
                existing = db_select(
                    "profiles",
                    {
                        "email":
                            f"eq.{email}",
                        "select":
                            "id",
                        "limit":
                            "1",
                    }
                )

                if existing:
                    flash(
                        "That email is already registered.",
                        "error"
                    )

                else:
                    rows = db_insert(
                        "profiles",
                        {
                            "full_name":
                                full_name,
                            "email":
                                email,
                            "phone":
                                phone,
                            "password_hash":
                                generate_password_hash(
                                    password
                                ),
                            "role":
                                "client",
                            "created_at":
                                now_iso(),
                        }
                    )

                    if rows:
                        flash(
                            "Account created successfully.",
                            "success"
                        )
                        return redirect(
                            url_for("login")
                        )

            except Exception as exc:
                logger.exception(exc)
                flash(
                    "Unable to create account. "
                    "Check the Supabase configuration.",
                    "error"
                )

    body = """
    <div class="card">
      <h2>Create KOJA Account</h2>

      <p class="small">
        Create a client account before submitting a service request.
      </p>

      <form method="post">

        <div class="grid">

          <div class="field">
            <label>Full Name *</label>
            <input name="full_name"
                   required>
          </div>

          <div class="field">
            <label>Phone</label>
            <input name="phone">
          </div>

          <div class="field">
            <label>Email *</label>
            <input type="email"
                   name="email"
                   required>
          </div>

          <div class="field">
            <label>Password *</label>
            <input type="password"
                   name="password"
                   required>
          </div>

          <div class="field">
            <label>Confirm Password *</label>
            <input type="password"
                   name="confirm_password"
                   required>
          </div>

        </div>

        <button class="btn green">
          Create Account
        </button>

      </form>
    </div>
    """

    return page(
        "Create Account",
        body
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

        try:
            rows = db_select(
                "profiles",
                {
                    "email":
                        f"eq.{email}",
                    "select":
                        "*",
                    "limit":
                        "1",
                }
            )

            user = rows[0] if rows else None

            if (
                user
                and check_password_hash(
                    user["password_hash"],
                    password
                )
            ):

                session.clear()

                session["user_id"] = user["id"]

                return redirect(
                    url_for("dashboard")
                )

        except Exception as exc:
            logger.exception(exc)

        flash(
            "Invalid email or password.",
            "error"
        )

    body = """
    <div class="card"
         style="max-width:600px;margin:auto">

      <h2>Client Login</h2>

      <form method="post">

        <div class="field">
          <label>Email *</label>
          <input type="email"
                 name="email"
                 required>
        </div>

        <div class="field">
          <label>Password *</label>
          <input type="password"
                 name="password"
                 required>
        </div>

        <button class="btn">
          Login
        </button>

      </form>

      <div class="actions">
        <a class="btn light"
           href="/register">
           Create Account
        </a>
      </div>

    </div>
    """

    return page(
        "Client Login",
        body
    )


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

    user = current_user()

    if not user:
        session.clear()
        return redirect(
            url_for("login")
        )

    rows = db_select(
        "service_requests",
        {
            "user_id":
                f"eq.{user['id']}",
            "select":
                "*",
            "order":
                "created_at.desc",
        }
    )

    counts = {}

    for status in STATUSES:
        counts[status] = len([
            r for r in rows
            if r["status"] == status
        ])

    recent = rows[:5]

    cards = ""

    for status in STATUSES:
        cards += f"""
        <div class="service">
          <strong>{status}</strong>
          <div class="big-number">
            {counts[status]}
          </div>
        </div>
        """

    table = ""

    for row in recent:

        status_class = (
            "completed"
            if row["status"] == "Completed"
            else
            "processing"
            if row["status"] == "Processing"
            else
            "rejected"
            if row["status"] == "Rejected"
            else
            "received"
        )

        table += f"""
        <tr>
          <td>
            <a href="/request/{row['id']}">
              <strong>
                {row['request_no']}
              </strong>
            </a>
          </td>

          <td>
            {row['service_name']}
          </td>

          <td>
            <span class="status {status_class}">
              {row['status']}
            </span>
          </td>
        </tr>
        """

    body = f"""
    <section class="hero">
      <h1>
        Welcome, {user['full_name']}
      </h1>

      <p>
        Submit a service request and monitor
        the progress from your KOJA client portal.
      </p>

      <a class="btn green"
         href="/services">
         Open KOJA Services
      </a>
    </section>

    <div class="grid3">
      {cards}
    </div>

    <section class="card">
      <h2>Recent Requests</h2>

      <table class="data-table">

        <tr>
          <th>Request</th>
          <th>Service</th>
          <th>Status</th>
        </tr>

        {table or
        '<tr><td colspan="3">No requests yet.</td></tr>'}

      </table>
    </section>
    """

    return page(
        "Dashboard",
        body
    )


# ============================================================
# SERVICES
# ============================================================

@app.route("/services")
@login_required
def services():

    cards = ""

    for key, name, description in SERVICE_LIST:

        cards += f"""
        <div class="service">

          <h3>{name}</h3>

          <p>{description}</p>

          <a class="btn green"
             href="/request/{key}">
             Open Service
          </a>

        </div>
        """

    body = f"""
    <section class="card">

      <h2>KOJA Services</h2>

      <p>
        Choose one service. Each service has
        its own workflow.
      </p>

      <div class="grid">
        {cards}
      </div>

    </section>
    """

    return page(
        "Services",
        body
    )


# ============================================================
# FARMER STEP 1
# ============================================================

@app.route(
    "/request/farmer",
    methods=["GET", "POST"]
)
@login_required
def farmer_step1():

    if request.method == "POST":

        try:

            data = {
                "nrc":
                    clean_required(
                        "nrc",
                        "NRC"
                    ),

                "date_of_birth":
                    clean_required(
                        "date_of_birth",
                        "Date of birth"
                    ),

                "first_name":
                    clean_required(
                        "first_name",
                        "First name"
                    ),

                "middle_names":
                    request.form.get(
                        "middle_names",
                        ""
                    ).strip(),

                "last_name":
                    clean_required(
                        "last_name",
                        "Last name"
                    ),

                "gender":
                    clean_required(
                        "gender",
                        "Gender"
                    ),

                "phone":
                    clean_required(
                        "phone",
                        "Phone"
                    ),
            }

            session["farmer_data"] = data

            return redirect(
                url_for(
                    "farmer_step2"
                )
            )

        except ValueError as exc:
            flash(
                str(exc),
                "error"
            )

    body = """
    <div class="card">

      <h2 style="text-align:center">
        Farmer Registration
      </h2>

      <div class="stepbar">
        <div class="step active">1</div>
        <div class="step">2</div>
        <div class="step">3</div>
      </div>

      <h2>Step 1: Personal Details</h2>

      <form method="post">

        <div class="grid">

          <div class="field">
            <label>NRC *</label>
            <input name="nrc"
                   required>
          </div>

          <div class="field">
            <label>Date of Birth *</label>
            <input type="date"
                   name="date_of_birth"
                   required>
          </div>

          <div class="field">
            <label>First Name *</label>
            <input name="first_name"
                   required>
          </div>

          <div class="field">
            <label>Middle Names</label>
            <input name="middle_names">
          </div>

          <div class="field">
            <label>Last Name *</label>
            <input name="last_name"
                   required>
          </div>

          <div class="field">
            <label>Gender *</label>
            <select name="gender"
                    required>
              <option value="">
                Select
              </option>
              <option>Male</option>
              <option>Female</option>
              <option>Other</option>
            </select>
          </div>

          <div class="field">
            <label>Phone *</label>
            <input name="phone"
                   required>
          </div>

        </div>

        <button class="btn green">
          Continue →
        </button>

      </form>

    </div>
    """

    return page(
        "Farmer Registration",
        body
    )


# ============================================================
# FARMER STEP 2
# ============================================================

@app.route(
    "/request/farmer/location",
    methods=["GET", "POST"]
)
@login_required
def farmer_step2():

    if "farmer_data" not in session:
        return redirect(
            url_for("farmer_step1")
        )

    if request.method == "POST":

        try:

            data = dict(
                session["farmer_data"]
            )

            data.update({
                "province":
                    clean_required(
                        "province",
                        "Province"
                    ),

                "district":
                    clean_required(
                        "district",
                        "District"
                    ),

                "constituency":
                    request.form.get(
                        "constituency",
                        ""
                    ).strip(),

                "chiefdom":
                    request.form.get(
                        "chiefdom",
                        ""
                    ).strip(),

                "farming_area":
                    clean_required(
                        "farming_area",
                        "Farming location"
                    ),
            })

            session["farmer_data"] = data

            return redirect(
                url_for(
                    "farmer_step3"
                )
            )

        except ValueError as exc:
            flash(
                str(exc),
                "error"
            )

    province_options = "".join(
        f"<option>{p}</option>"
        for p in PROVINCES
    )

    body = f"""
    <div class="card">

      <h2 style="text-align:center">
        Farmer Registration
      </h2>

      <div class="stepbar">
        <div class="step done">✓</div>
        <div class="step active">2</div>
        <div class="step">3</div>
      </div>

      <h2>Step 2: Location</h2>

      <form method="post">

        <div class="field">
          <label>Province *</label>
          <select name="province"
                  required>
            <option value="">
              Select Province
            </option>
            {province_options}
          </select>
        </div>

        <div class="grid">

          <div class="field">
            <label>District *</label>
            <input name="district"
                   required>
          </div>

          <div class="field">
            <label>Constituency</label>
            <input name="constituency">
          </div>

          <div class="field">
            <label>Chiefdom</label>
            <input name="chiefdom">
          </div>

          <div class="field">
            <label>Farming Location / Area *</label>
            <input name="farming_area"
                   required>
          </div>

        </div>

        <div class="actions">

          <a class="btn light"
             href="/request/farmer">
             ← Back
          </a>

          <button class="btn green">
            Continue →
          </button>

        </div>

      </form>

    </div>
    """

    return page(
        "Farmer Location",
        body
    )


# ============================================================
# FARMER STEP 3
# ============================================================

@app.route(
    "/request/farmer/payment",
    methods=["GET", "POST"]
)
@login_required
def farmer_step3():

    if "farmer_data" not in session:
        return redirect(
            url_for("farmer_step1")
        )

    if request.method == "POST":

        try:

            data = dict(
                session["farmer_data"]
            )

            data.update({

                "payment_method":
                    clean_required(
                        "payment_method",
                        "Payment method"
                    ),

                "provider":
                    clean_required(
                        "provider",
                        "Provider"
                    ),

                "branch":
                    request.form.get(
                        "branch",
                        ""
                    ).strip(),

                "account_no":
                    clean_required(
                        "account_no",
                        "Account number"
                    ),

                "account_name":
                    clean_required(
                        "account_name",
                        "Account name"
                    ),
            })

            user = current_user()

            request_id, request_no = create_request(
                user["id"],
                "farmer",
                data
            )

            upload = request.files.get(
                "nrc_card"
            )

            if upload and upload.filename:
                attach_file(
                    request_id,
                    upload,
                    "client"
                )

            session.pop(
                "farmer_data",
                None
            )

            flash(
                f"Farmer request {request_no} submitted.",
                "success"
            )

            return redirect(
                url_for(
                    "request_detail",
                    request_id=request_id
                )
            )

        except ValueError as exc:
            flash(
                str(exc),
                "error"
            )

        except Exception as exc:
            logger.exception(exc)
            flash(
                "Unable to submit the request.",
                "error"
            )

    banks = json.dumps(BANKS)
    mobiles = json.dumps(
        MOBILE_PROVIDERS
    )

    body = f"""
    <div class="card">

      <h2 style="text-align:center">
        Farmer Registration
      </h2>

      <div class="stepbar">
        <div class="step done">✓</div>
        <div class="step done">✓</div>
        <div class="step active">3</div>
      </div>

      <h2>Step 3: Payment & Submit</h2>

      <form method="post"
            enctype="multipart/form-data">

        <div class="field">
          <label>Payment Method *</label>

          <select name="payment_method"
                  id="payment_method"
                  onchange="updateProviders()"
                  required>

            <option value="">
              Select method
            </option>

            <option>Bank Account</option>
            <option>Mobile Money</option>

          </select>
        </div>

        <div class="field">

          <label>Provider *</label>

          <select name="provider"
                  id="provider"
                  required>

            <option value="">
              Select provider
            </option>

          </select>

        </div>

        <div class="field">
          <label>Branch</label>
          <input name="branch">
        </div>

        <div class="grid">

          <div class="field">
            <label>Account Number *</label>
            <input name="account_no"
                   required>
          </div>

          <div class="field">
            <label>Account Name *</label>
            <input name="account_name"
                   required>
          </div>

        </div>

        <div class="field filebox">

          <label>NRC / Supporting Document</label>

          <input type="file"
                 name="nrc_card"
                 accept=".pdf,.doc,.docx,.jpg,.jpeg,.png,.webp">

          <div class="small">
            Maximum 10 MB.
          </div>

        </div>

        <div class="actions">

          <a class="btn light"
             href="/request/farmer/location">
             ← Back
          </a>

          <button class="btn green">
            Submit Farmer Request
          </button>

        </div>

      </form>

    </div>

    <script>

    const banks = {banks};
    const mobiles = {mobiles};

    function updateProviders() {{

      const method =
        document.getElementById(
          "payment_method"
        ).value;

      const provider =
        document.getElementById(
          "provider"
        );

      provider.innerHTML =
        '<option value="">Select provider</option>';

      let list = [];

      if(method === "Bank Account") {{
        list = banks;
      }}

      if(method === "Mobile Money") {{
        list = mobiles;
      }}

      list.forEach(function(item) {{

        const option =
          document.createElement(
            "option"
          );

        option.value = item;
        option.textContent = item;

        provider.appendChild(option);

      }});

    }}

    </script>
    """

    return page(
        "Farmer Payment",
        body
    )


# ============================================================
# TPIN
# ============================================================

@app.route(
    "/request/tpin",
    methods=["GET", "POST"]
)
@login_required
def tpin_request():

    if request.method == "POST":

        try:

            data = {

                "nrc_number":
                    clean_required(
                        "nrc_number",
                        "NRC number"
                    ),

                "date_of_birth":
                    clean_required(
                        "date_of_birth",
                        "Date of birth"
                    ),

                "first_name":
                    clean_required(
                        "first_name",
                        "First name"
                    ),

                "middle_names":
                    request.form.get(
                        "middle_names",
                        ""
                    ).strip(),

                "last_name":
                    clean_required(
                        "last_name",
                        "Last name"
                    ),

                "gender":
                    clean_required(
                        "gender",
                        "Gender"
                    ),

                "phone_number":
                    clean_required(
                        "phone_number",
                        "Phone number"
                    ),

                "email":
                    clean_required(
                        "email",
                        "Email"
                    ),

                "house_number":
                    clean_required(
                        "house_number",
                        "House number"
                    ),

                "province":
                    clean_required(
                        "province",
                        "Province"
                    ),

                "district":
                    clean_required(
                        "district",
                        "District"
                    ),

                "post_address":
                    clean_required(
                        "post_address",
                        "Post address"
                    ),

                "request_type":
                    clean_required(
                        "request_type",
                        "TPIN service"
                    ),

                "additional_information":
                    request.form.get(
                        "additional_information",
                        ""
                    ).strip(),
            }

            user = current_user()

            request_id, request_no = create_request(
                user["id"],
                "tpin",
                data
            )

            for upload in request.files.getlist(
                "supporting_documents"
            ):

                if upload and upload.filename:
                    attach_file(
                        request_id,
                        upload,
                        "client"
                    )

            flash(
                f"TPIN request {request_no} submitted.",
                "success"
            )

            return redirect(
                url_for(
                    "request_detail",
                    request_id=request_id
                )
            )

        except ValueError as exc:
            flash(
                str(exc),
                "error"
            )

        except Exception as exc:
            logger.exception(exc)
            flash(
                "Unable to submit TPIN request.",
                "error"
            )

    province_options = "".join(
        f"<option>{p}</option>"
        for p in PROVINCES
    )

    body = f"""
    <div class="card">

      <h2>TPIN Services</h2>

      <p>
        Submit your TPIN-related request
        and supporting documents.
      </p>

      <form method="post"
            enctype="multipart/form-data">

        <div class="grid">

          <div class="field">
            <label>NRC Number *</label>
            <input name="nrc_number"
                   required>
          </div>

          <div class="field">
            <label>Date of Birth *</label>
            <input type="date"
                   name="date_of_birth"
                   required>
          </div>

          <div class="field">
            <label>First Name *</label>
            <input name="first_name"
                   required>
          </div>

          <div class="field">
            <label>Middle Names</label>
            <input name="middle_names">
          </div>

          <div class="field">
            <label>Last Name *</label>
            <input name="last_name"
                   required>
          </div>

          <div class="field">
            <label>Gender *</label>
            <select name="gender"
                    required>
              <option value="">
                Select
              </option>
              <option>Male</option>
              <option>Female</option>
              <option>Other</option>
            </select>
          </div>

          <div class="field">
            <label>Phone *</label>
            <input name="phone_number"
                   required>
          </div>

          <div class="field">
            <label>Email *</label>
            <input type="email"
                   name="email"
                   required>
          </div>

          <div class="field">
            <label>House Number *</label>
            <input name="house_number"
                   required>
          </div>

          <div class="field">
            <label>Province *</label>
            <select name="province"
                    required>
              <option value="">
                Select
              </option>
              {province_options}
            </select>
          </div>

          <div class="field">
            <label>District *</label>
            <input name="district"
                   required>
          </div>

          <div class="field">
            <label>Post Address *</label>
            <input name="post_address"
                   required>
          </div>

          <div class="field">
            <label>TPIN Service *</label>

            <select name="request_type"
                    required>

              <option value="">
                Select
              </option>

              <option>
                TPIN Registration
              </option>

              <option>
                TPIN Certificate / Document Request
              </option>

              <option>
                TPIN Update
              </option>

              <option>
                TPIN Assistance
              </option>

              <option>
                Other TPIN Service
              </option>

            </select>

          </div>

        </div>

        <div class="field">
          <label>Additional Information</label>

          <textarea
            name="additional_information"></textarea>
        </div>

        <div class="field filebox">

          <label>Supporting Documents</label>

          <input type="file"
                 name="supporting_documents"
                 multiple
                 accept=".pdf,.doc,.docx,.xls,.xlsx,.jpg,.jpeg,.png,.webp">

          <div class="small">
            Maximum 10 MB per file.
          </div>

        </div>

        <button class="btn">
          Submit TPIN Request
        </button>

      </form>

    </div>
    """

    return page(
        "TPIN Services",
        body
    )


# ============================================================
# UNIVERSITY
# ============================================================

@app.route(
    "/request/university",
    methods=["GET", "POST"]
)
@login_required
def university_request():

    if request.method == "POST":

        try:

            data = {

                "university":
                    clean_required(
                        "university",
                        "University"
                    ),

                "request_type":
                    clean_required(
                        "request_type",
                        "Request type"
                    ),

                "student_number":
                    request.form.get(
                        "student_number",
                        ""
                    ).strip(),

                "programme":
                    request.form.get(
                        "programme",
                        ""
                    ).strip(),

                "academic_level":
                    request.form.get(
                        "academic_level",
                        ""
                    ).strip(),

                "description":
                    clean_required(
                        "description",
                        "Description"
                    ),
            }

            user = current_user()

            request_id, request_no = create_request(
                user["id"],
                "university",
                data
            )

            for upload in request.files.getlist(
                "documents"
            ):

                if upload and upload.filename:
                    attach_file(
                        request_id,
                        upload,
                        "client"
                    )

            flash(
                f"University request {request_no} submitted.",
                "success"
            )

            return redirect(
                url_for(
                    "request_detail",
                    request_id=request_id
                )
            )

        except ValueError as exc:
            flash(
                str(exc),
                "error"
            )

        except Exception as exc:
            logger.exception(exc)
            flash(
                "Unable to submit university request.",
                "error"
            )

    body = """
    <div class="card">

      <h2>University Request</h2>

      <form method="post"
            enctype="multipart/form-data">

        <div class="grid">

          <div class="field">
            <label>University *</label>
            <input name="university"
                   required>
          </div>

          <div class="field">
            <label>Request Type *</label>

            <select name="request_type"
                    required>

              <option value="">
                Select
              </option>

              <option>
                Application Assistance
              </option>

              <option>
                Academic Request
              </option>

              <option>
                Student Records Request
              </option>

              <option>
                Verification Request
              </option>

              <option>
                Other University Request
              </option>

            </select>

          </div>

          <div class="field">
            <label>Student Number</label>
            <input name="student_number">
          </div>

          <div class="field">
            <label>Programme</label>
            <input name="programme">
          </div>

          <div class="field">
            <label>Academic Level</label>
            <input name="academic_level">
          </div>

        </div>

        <div class="field">
          <label>Description *</label>
          <textarea name="description"
                    required></textarea>
        </div>

        <div class="field filebox">

          <label>Supporting Documents</label>

          <input type="file"
                 name="documents"
                 multiple
                 accept=".pdf,.doc,.docx,.xls,.xlsx,.jpg,.jpeg,.png,.webp">

        </div>

        <button class="btn">
          Submit University Request
        </button>

      </form>

    </div>
    """

    return page(
        "University Request",
        body
    )


# ============================================================
# ASSIGNMENT / QUESTION SERVICE
# ============================================================

@app.route(
    "/request/assignment",
    methods=["GET", "POST"]
)
@login_required
def assignment_request():

    if request.method == "POST":

        try:

            title = clean_required(
                "title",
                "Assignment / question title"
            )

            subject = clean_required(
                "subject",
                "Subject"
            )

            question = request.form.get(
                "question",
                ""
            ).strip()

            instructions = request.form.get(
                "instructions",
                ""
            ).strip()

            education_level = request.form.get(
                "education_level",
                ""
            ).strip()

            if not question and not request.files.get(
                "assignment_file"
            ):
                raise ValueError(
                    "Enter a question or upload an assignment."
                )

            data = {
                "title":
                    title,

                "subject":
                    subject,

                "question":
                    question,

                "instructions":
                    instructions,

                "education_level":
                    education_level,

                "request_mode":
                    (
                        "Question"
                        if question and not request.files.get(
                            "assignment_file"
                        )
                        else
                        "Assignment Upload"
                        if request.files.get(
                            "assignment_file"
                        )
                        else
                        "Question + Assignment"
                    ),
            }

            user = current_user()

            request_id, request_no = create_request(
                user["id"],
                "assignment",
                data
            )

            assignment_file = request.files.get(
                "assignment_file"
            )

            if assignment_file and assignment_file.filename:
                attach_file(
                    request_id,
                    assignment_file,
                    "assignment"
                )

            for upload in request.files.getlist(
                "supporting_documents"
            ):

                if upload and upload.filename:
                    attach_file(
                        request_id,
                        upload,
                        "supporting"
                    )

            flash(
                f"Assignment/question {request_no} submitted successfully.",
                "success"
            )

            return redirect(
                url_for(
                    "request_detail",
                    request_id=request_id
                )
            )

        except ValueError as exc:
            flash(
                str(exc),
                "error"
            )

        except Exception as exc:
            logger.exception(exc)
            flash(
                "Unable to submit assignment.",
                "error"
            )

    body = """
    <div class="card">

      <h2>
        Assignment / Question Request
      </h2>

      <p>
        Ask a question directly, upload your
        assignment, or do both.
      </p>

      <form method="post"
            enctype="multipart/form-data">

        <div class="grid">

          <div class="field">
            <label>Assignment / Question Title *</label>
            <input name="title"
                   placeholder="Example: Biology Assignment 1"
                   required>
          </div>

          <div class="field">
            <label>Subject *</label>
            <input name="subject"
                   placeholder="Example: Biology"
                   required>
          </div>

          <div class="field">
            <label>Education Level</label>
            <input name="education_level"
                   placeholder="Grade / Diploma / Degree">
          </div>

        </div>

        <div class="field">
          <label>Your Question</label>

          <textarea
            name="question"
            placeholder="Type your question here."></textarea>
        </div>

        <div class="field">

          <label>
            Assignment / Question File
          </label>

          <div class="filebox">

            <input type="file"
                   name="assignment_file"
                   accept=".pdf,.doc,.docx,.xls,.xlsx,.jpg,.jpeg,.png,.webp">

            <div class="small">
              PDF, Word, Excel or image.
              Maximum 10 MB.
            </div>

          </div>

        </div>

        <div class="field">
          <label>Instructions for KOJA</label>

          <textarea
            name="instructions"
            placeholder="Explain what you want KOJA to do."></textarea>
        </div>

        <div class="field filebox">

          <label>Additional Supporting Documents</label>

          <input type="file"
                 name="supporting_documents"
                 multiple
                 accept=".pdf,.doc,.docx,.xls,.xlsx,.jpg,.jpeg,.png,.webp">

        </div>

        <button class="btn green">
          Submit Assignment / Question
        </button>

      </form>

    </div>
    """

    return page(
        "Assignment / Question",
        body
    )


# ============================================================
# OTHER
# ============================================================

@app.route(
    "/request/other",
    methods=["GET", "POST"]
)
@login_required
def other_request():

    if request.method == "POST":

        try:

            data = {

                "service_title":
                    clean_required(
                        "service_title",
                        "Service title"
                    ),

                "description":
                    clean_required(
                        "description",
                        "Description"
                    ),

                "additional_information":
                    request.form.get(
                        "additional_information",
                        ""
                    ).strip(),
            }

            user = current_user()

            request_id, request_no = create_request(
                user["id"],
                "other",
                data
            )

            for upload in request.files.getlist(
                "documents"
            ):

                if upload and upload.filename:
                    attach_file(
                        request_id,
                        upload,
                        "client"
                    )

            flash(
                f"Service request {request_no} submitted.",
                "success"
            )

            return redirect(
                url_for(
                    "request_detail",
                    request_id=request_id
                )
            )

        except ValueError as exc:
            flash(
                str(exc),
                "error"
            )

        except Exception as exc:
            logger.exception(exc)
            flash(
                "Unable to submit request.",
                "error"
            )

    body = """
    <div class="card">

      <h2>Other KOJA Service</h2>

      <form method="post"
            enctype="multipart/form-data">

        <div class="field">
          <label>Service / Request Title *</label>
          <input name="service_title"
                 required>
        </div>

        <div class="field">
          <label>Description *</label>
          <textarea name="description"
                    required></textarea>
        </div>

        <div class="field">
          <label>Additional Information</label>
          <textarea
            name="additional_information"></textarea>
        </div>

        <div class="field filebox">

          <label>Documents</label>

          <input type="file"
                 name="documents"
                 multiple
                 accept=".pdf,.doc,.docx,.xls,.xlsx,.jpg,.jpeg,.png,.webp">

        </div>

        <button class="btn">
          Submit Request
        </button>

      </form>

    </div>
    """

    return page(
        "Other Services",
        body
    )


# ============================================================
# MY REQUESTS
# ============================================================

@app.route("/my-requests")
@login_required
def my_requests():

    user = current_user()

    rows = db_select(
        "service_requests",
        {
            "user_id":
                f"eq.{user['id']}",
            "select":
                "*",
            "order":
                "created_at.desc",
        }
    )

    table = ""

    for row in rows:

        status_class = (
            "completed"
            if row["status"] == "Completed"
            else
            "processing"
            if row["status"] == "Processing"
            else
            "rejected"
            if row["status"] == "Rejected"
            else
            "received"
        )

        table += f"""
        <tr>

          <td>
            <a href="/request/{row['id']}">
              <strong>
                {row['request_no']}
              </strong>
            </a>
          </td>

          <td>
            {row['service_name']}
          </td>

          <td>
            {str(row['created_at'])[:10]}
          </td>

          <td>
            <span class="status {status_class}">
              {row['status']}
            </span>
          </td>

        </tr>
        """

    body = f"""
    <div class="card">

      <h2>My Requests</h2>

      <table class="data-table">

        <tr>
          <th>Request</th>
          <th>Service</th>
          <th>Date</th>
          <th>Status</th>
        </tr>

        {table or
        '<tr><td colspan="4">No requests.</td></tr>'}

      </table>

    </div>
    """

    return page(
        "My Requests",
        body
    )


# ============================================================
# REQUEST DETAIL
# ============================================================

@app.route(
    "/request/<request_id>"
)
@login_required
def request_detail(request_id):

    row = get_request(request_id)

    if not row:
        abort(404)

    user = current_user()

    if str(row["user_id"]) != str(
        user["id"]
    ):
        abort(403)

    data = row.get(
        "data_json",
        {}
    )

    if isinstance(data, str):
        try:
            data = json.loads(data)
        except Exception:
            data = {}

    files = get_request_files(
        request_id
    )

    status_class = (
        "completed"
        if row["status"] == "Completed"
        else
        "processing"
        if row["status"] == "Processing"
        else
        "rejected"
        if row["status"] == "Rejected"
        else
        "received"
    )

    details = ""

    for key, value in data.items():

        details += f"""
        <div class="k">
          {key.replace('_',' ').title()}
        </div>

        <div>
          {str(value).replace(chr(10), '<br>')}
        </div>
        """

    file_html = ""

    for file in files:

        file_html += f"""
        <li>
          <a href="/file/{file['id']}">
            {file['original_name']}
          </a>
        </li>
        """

    result = ""

    if row.get("result_file_path"):

        result = f"""
        <section class="card">

          <h2>KOJA Answer / Result</h2>

          <div class="answer-box">
            {row.get('admin_response') or
             'Your result is ready.'}
          </div>

          <div class="actions">

            <a class="btn green"
               href="/download-result/{row['id']}">
               Download Answer
            </a>

          </div>

        </section>
        """

    else:

        result = f"""
        <section class="card">

          <h2>KOJA Response</h2>

          <div class="answer-box">
            {row.get('admin_response') or
             'KOJA has not added a response yet.'}
          </div>

        </section>
        """

    body = f"""

    <section class="card">

      <h2>{row['request_no']}</h2>

      <p>
        <strong>Service:</strong>
        {row['service_name']}
      </p>

      <p>
        <strong>Status:</strong>

        <span class="status {status_class}">
          {row['status']}
        </span>
      </p>

      <p class="small">
        Submitted:
        {row['created_at']}
      </p>

    </section>

    <section class="card">

      <h2>Submitted Information</h2>

      <div class="kv">
        {details}
      </div>

    </section>

    <section class="card">

      <h2>Uploaded Documents</h2>

      <ul>
        {file_html or '<li>No documents.</li>'}
      </ul>

    </section>

    {result}
    """

    return page(
        row["request_no"],
        body
    )


# ============================================================
# CLIENT FILE DOWNLOAD
# ============================================================

@app.route(
    "/file/<file_id>"
)
@login_required
def client_file(file_id):

    rows = db_select(
        "request_files",
        {
            "id":
                f"eq.{file_id}",
            "select":
                "*",
            "limit":
                "1",
        }
    )

    if not rows:
        abort(404)

    file = rows[0]

    row = get_request(
        file["request_id"]
    )

    if not row:
        abort(404)

    user = current_user()

    if str(row["user_id"]) != str(
        user["id"]
    ):
        abort(403)

    try:

        content = storage_download(
            file["storage_path"]
        )

        return send_file(
            io.BytesIO(content),
            mimetype=file.get(
                "mime_type",
                "application/octet-stream"
            ),
            as_attachment=True,
            download_name=file[
                "original_name"
            ],
        )

    except Exception as exc:
        logger.exception(exc)
        abort(404)


# ============================================================
# RESULT DOWNLOAD
# ============================================================

@app.route(
    "/download-result/<request_id>"
)
@login_required
def download_result(request_id):

    row = get_request(
        request_id
    )

    if not row:
        abort(404)

    user = current_user()

    if str(row["user_id"]) != str(
        user["id"]
    ):
        abort(403)

    path = row.get(
        "result_file_path"
    )

    if not path:
        abort(404)

    try:

        content = storage_download(
            path
        )

        filename = (
            row.get(
                "result_file_name"
            )
            or
            "KOJA-Answer"
        )

        extension = (
            filename.rsplit(
                ".",
                1
            )[-1].lower()
            if "." in filename
            else ""
        )

        mime_types = {
            "pdf":
                "application/pdf",

            "doc":
                "application/msword",

            "docx":
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",

            "xls":
                "application/vnd.ms-excel",

            "xlsx":
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",

            "jpg":
                "image/jpeg",

            "jpeg":
                "image/jpeg",

            "png":
                "image/png",

            "webp":
                "image/webp",
        }

        return send_file(
            io.BytesIO(content),
            mimetype=mime_types.get(
                extension,
                "application/octet-stream"
            ),
            as_attachment=True,
            download_name=filename,
        )

    except Exception as exc:
        logger.exception(exc)
        abort(404)


# ============================================================
# NOTIFICATIONS
# ============================================================

@app.route("/notifications")
@login_required
def notifications():

    user = current_user()

    rows = db_select(
        "notifications",
        {
            "user_id":
                f"eq.{user['id']}",
            "select":
                "*",
            "order":
                "created_at.desc",
        }
    )

    try:

        db_update(
            "notifications",
            {
                "user_id":
                    f"eq.{user['id']}"
            },
            {
                "is_read":
                    True
            }
        )

    except Exception:
        pass

    cards = ""

    for row in rows:

        cards += f"""
        <div class="card">

          <h3>{row['title']}</h3>

          <p>
            {row['message']}
          </p>

          <div class="small">
            {row['created_at']}
          </div>

        </div>
        """

    body = (
        cards
        or
        """
        <div class="card">
          <h2>Notifications</h2>
          <p>No notifications.</p>
        </div>
        """
    )

    return page(
        "Notifications",
        body
    )


# ============================================================
# PROFILE
# ============================================================

@app.route("/profile")
@login_required
def profile():

    user = current_user()

    body = f"""
    <div class="card">

      <h2>My Profile</h2>

      <div class="kv">

        <div class="k">
          Full Name
        </div>
        <div>
          {user['full_name']}
        </div>

        <div class="k">
          Email
        </div>
        <div>
          {user['email']}
        </div>

        <div class="k">
          Phone
        </div>
        <div>
          {user.get('phone') or ''}
        </div>

        <div class="k">
          Account Created
        </div>
        <div>
          {user.get('created_at') or ''}
        </div>

      </div>

    </div>
    """

    return page(
        "Profile",
        body
    )


# ============================================================
# ADMIN LOGIN
# ============================================================

@app.route(
    "/admin/login",
    methods=["GET", "POST"]
)
def admin_login():

    if request.method == "POST":

        email = request.form.get(
            "email",
            ""
        ).strip().lower()

        password = request.form.get(
            "password",
            ""
        )

        if (
            secrets.compare_digest(
                email,
                ADMIN_EMAIL
            )
            and
            secrets.compare_digest(
                password,
                ADMIN_PASSWORD
            )
        ):

            session.clear()

            session[
                "admin_logged_in"
            ] = True

            return redirect(
                url_for(
                    "admin_dashboard"
                )
            )

        flash(
            "Invalid administrator credentials.",
            "error"
        )

    body = """
    <div class="card"
         style="max-width:600px;margin:auto">

      <h2>KOJA Administrator Login</h2>

      <p class="small">
        Administrator access is separate
        from client accounts.
      </p>

      <form method="post">

        <div class="field">
          <label>Admin Email *</label>
          <input type="email"
                 name="email"
                 required>
        </div>

        <div class="field">
          <label>Admin Password *</label>
          <input type="password"
                 name="password"
                 required>
        </div>

        <button class="btn">
          Admin Login
        </button>

      </form>

    </div>
    """

    return page(
        "Admin Login",
        body
    )


@app.route("/admin/logout")
def admin_logout():

    session.clear()

    return redirect(
        url_for("admin_login")
    )


# ============================================================
# ADMIN DASHBOARD
# ============================================================

@app.route("/admin")
@admin_required
def admin_dashboard():

    rows = db_select(
        "service_requests",
        {
            "select":
                "*",
            "order":
                "created_at.desc",
        }
    )

    total = len(rows)

    received = len([
        r for r in rows
        if r["status"] == "Request Received"
    ])

    processing = len([
        r for r in rows
        if r["status"] == "Processing"
    ])

    completed = len([
        r for r in rows
        if r["status"] == "Completed"
    ])

    rejected = len([
        r for r in rows
        if r["status"] == "Rejected"
    ])

    cards = f"""
    <div class="grid3">

      <div class="service">
        <strong>Total Requests</strong>
        <div class="big-number">
          {total}
        </div>
      </div>

      <div class="service">
        <strong>Received</strong>
        <div class="big-number">
          {received}
        </div>
      </div>

      <div class="service">
        <strong>Processing</strong>
        <div class="big-number">
          {processing}
        </div>
      </div>

      <div class="service">
        <strong>Completed</strong>
        <div class="big-number">
          {completed}
        </div>
      </div>

      <div class="service">
        <strong>Rejected</strong>
        <div class="big-number">
          {rejected}
        </div>
      </div>

    </div>
    """

    table = ""

    for row in rows[:200]:

        status_class = (
            "completed"
            if row["status"] == "Completed"
            else
            "processing"
            if row["status"] == "Processing"
            else
            "rejected"
            if row["status"] == "Rejected"
            else
            "received"
        )

        user_rows = db_select(
            "profiles",
            {
                "id":
                    f"eq.{row['user_id']}",
                "select":
                    "full_name,email",
                "limit":
                    "1",
            }
        )

        user = (
            user_rows[0]
            if user_rows
            else {}
        )

        table += f"""
        <tr>

          <td>
            <a href="/admin/request/{row['id']}">
              <strong>
                {row['request_no']}
              </strong>
            </a>
          </td>

          <td>
            {row['service_name']}
          </td>

          <td>
            {user.get('full_name','')}
          </td>

          <td>
            {user.get('email','')}
          </td>

          <td>
            <span class="status {status_class}">
              {row['status']}
            </span>
          </td>

        </tr>
        """

    body = f"""

    <section class="hero">

      <h1>Admin Dashboard</h1>

      <p>
        Process farmer, TPIN, university,
        assignment and other service requests.
      </p>

    </section>

    {cards}

    <section class="card">

      <h2>Requests</h2>

      <table class="data-table">

        <tr>
          <th>Request</th>
          <th>Service</th>
          <th>Client</th>
          <th>Email</th>
          <th>Status</th>
        </tr>

        {table or
        '<tr><td colspan="5">No requests.</td></tr>'}

      </table>

    </section>

    """

    return page(
        "Admin Dashboard",
        body,
        admin=True
    )


# ============================================================
# ADMIN REQUEST PROCESSING
# ============================================================

@app.route(
    "/admin/request/<request_id>",
    methods=["GET", "POST"]
)
@admin_required
def admin_request_detail(request_id):

    row = get_request(
        request_id
    )

    if not row:
        abort(404)

    if request.method == "POST":

        status = request.form.get(
            "status",
            ""
        ).strip()

        response_text = request.form.get(
            "admin_response",
            ""
        ).strip()

        if status not in STATUSES:

            flash(
                "Invalid status.",
                "error"
            )

            return redirect(
                url_for(
                    "admin_request_detail",
                    request_id=request_id
                )
            )

        result_file = request.files.get(
            "result_file"
        )

        result_path = row.get(
            "result_file_path"
        )

        result_name = row.get(
            "result_file_name"
        )

        if result_file and result_file.filename:

            original = secure_filename(
                result_file.filename
            )

            if not original:
                flash(
                    "Invalid result filename.",
                    "error"
                )

                return redirect(
                    url_for(
                        "admin_request_detail",
                        request_id=request_id
                    )
                )

            extension = original.rsplit(
                ".",
                1
            )[-1].lower()

            if extension not in ALLOWED_RESULT_EXTENSIONS:
                flash(
                    "Unsupported answer file type.",
                    "error"
                )

                return redirect(
                    url_for(
                        "admin_request_detail",
                        request_id=request_id
                    )
                )

            folder = (
                f"requests/"
                f"{request_id}/"
                f"results"
            )

            info = storage_upload(
                result_file,
                folder
            )

            result_path = info[
                "path"
            ]

            result_name = info[
                "original_name"
            ]

        try:

            db_update(
                "service_requests",
                {
                    "id":
                        f"eq.{request_id}"
                },
                {
                    "status":
                        status,

                    "admin_response":
                        response_text,

                    "result_file_path":
                        result_path,

                    "result_file_name":
                        result_name,

                    "updated_at":
                        now_iso(),
                }
            )

            add_notification(
                row["user_id"],
                (
                    f"Request Updated: "
                    f"{row['request_no']}"
                ),
                (
                    f"Your {row['service_name']} "
                    f"request is now '{status}'. "
                    +
                    (
                        f"KOJA response: "
                        f"{response_text}"
                        if response_text
                        else
                        ""
                    )
                ),
            )

            flash(
                "Request updated successfully.",
                "success"
            )

            return redirect(
                url_for(
                    "admin_request_detail",
                    request_id=request_id
                )
            )

        except Exception as exc:

            logger.exception(exc)

            flash(
                "Unable to update request.",
                "error"
            )

    data = row.get(
        "data_json",
        {}
    )

    if isinstance(data, str):

        try:
            data = json.loads(data)
        except Exception:
            data = {}

    details = ""

    for key, value in data.items():

        details += f"""
        <div class="k">
          {key.replace('_',' ').title()}
        </div>

        <div>
          {str(value).replace(chr(10), '<br>')}
        </div>
        """

    files = get_request_files(
        request_id
    )

    file_html = ""

    for file in files:

        file_html += f"""
        <li>
          <a href="/admin/file/{file['id']}">
            {file['original_name']}
          </a>
          <span class="small">
            ({file.get('category','')})
          </span>
        </li>
        """

    options = ""

    for status in STATUSES:

        selected = (
            "selected"
            if row["status"] == status
            else
            ""
        )

        options += (
            f'<option {selected}>'
            f'{status}'
            f'</option>'
        )

    result_current = ""

    if row.get(
        "result_file_path"
    ):

        result_current = f"""
        <div class="alert success">
          Current result:
          <strong>
            {row.get('result_file_name')}
          </strong>
        </div>
        """

    body = f"""

    <section class="card">

      <h2>
        {row['request_no']}
      </h2>

      <p>
        <strong>
          Service:
        </strong>
        {row['service_name']}
      </p>

      <p>
        <strong>
          Client ID:
        </strong>
        {row['user_id']}
      </p>

    </section>

    <section class="card">

      <h2>
        Submitted Information
      </h2>

      <div class="kv">
        {details}
      </div>

    </section>

    <section class="card">

      <h2>
        Client Documents
      </h2>

      <ul>
        {file_html or
         '<li>No uploaded documents.</li>'}
      </ul>

    </section>

    <section class="card">

      <h2>
        Process Request
      </h2>

      <form method="post"
            enctype="multipart/form-data">

        <div class="field">

          <label>
            Status
          </label>

          <select name="status">
            {options}
          </select>

        </div>

        <div class="field">

          <label>
            Admin Answer / Response
          </label>

          <textarea
            name="admin_response"
            placeholder="Write the answer, instructions, progress update or result message.">{row.get('admin_response') or ''}</textarea>

        </div>

        <div class="field filebox">

          <label>
            Upload Completed Answer
          </label>

          <input type="file"
                 name="result_file"
                 accept=".pdf,.doc,.docx,.xls,.xlsx,.jpg,.jpeg,.png,.webp">

          <div class="small">
            Supported answer files:
            PDF, Word and Excel.
            Maximum 10 MB.
          </div>

        </div>

        {result_current}

        <button class="btn green">
          Save & Send Update
        </button>

      </form>

    </section>

    <a class="btn light"
       href="/admin">
       ← Admin Dashboard
    </a>

    """

    return page(
        "Process Request",
        body,
        admin=True
    )


# ============================================================
# ADMIN FILE
# ============================================================

@app.route(
    "/admin/file/<file_id>"
)
@admin_required
def admin_file(file_id):

    rows = db_select(
        "request_files",
        {
            "id":
                f"eq.{file_id}",
            "select":
                "*",
            "limit":
                "1",
        }
    )

    if not rows:
        abort(404)

    file = rows[0]

    try:

        content = storage_download(
            file["storage_path"]
        )

        return send_file(
            io.BytesIO(content),
            mimetype=file.get(
                "mime_type",
                "application/octet-stream"
            ),
            as_attachment=True,
            download_name=file[
                "original_name"
            ],
        )

    except Exception:
        abort(404)


# ============================================================
# ERROR HANDLERS
# ============================================================

@app.errorhandler(400)
def error_400(error):

    body = """
    <div class="card">
      <h1>400</h1>
      <p>
        The request could not be understood.
      </p>
      <a class="btn" href="/">
        Home
      </a>
    </div>
    """

    return page(
        "400",
        body
    ), 400


@app.errorhandler(403)
def error_403(error):

    body = """
    <div class="card">
      <h1>403</h1>
      <p>
        You do not have permission to access
        this page.
      </p>
      <a class="btn" href="/">
        Home
      </a>
    </div>
    """

    return page(
        "403",
        body
    ), 403


@app.errorhandler(404)
def error_404(error):

    body = """
    <div class="card">
      <h1>404</h1>
      <p>
        The requested page was not found.
      </p>
      <a class="btn" href="/">
        Home
      </a>
    </div>
    """

    return page(
        "404",
        body
    ), 404


@app.errorhandler(413)
def error_413(error):

    body = """
    <div class="card">
      <h1>File Too Large</h1>
      <p>
        The maximum upload size is 10 MB.
      </p>
      <a class="btn" href="/">
        Home
      </a>
    </div>
    """

    return page(
        "File Too Large",
        body
    ), 413


@app.errorhandler(Exception)
def error_500(error):

    logger.exception(
        "Unhandled application error"
    )

    body = """
    <div class="card">
      <h1>Application Error</h1>
      <p>
        KOJA encountered an unexpected error.
        Please try again.
      </p>
      <a class="btn" href="/">
        Return Home
      </a>
    </div>
    """

    return page(
        "Application Error",
        body
    ), 500


# ============================================================
# HEALTH CHECK
# ============================================================

@app.route("/health")
def health():

    return {
        "status": "ok",
        "application": "KOJA AFRICA",
        "database": (
            "configured"
            if SUPABASE_URL
            and SUPABASE_SERVICE_KEY
            else
            "not configured"
        ),
        "storage_bucket":
            STORAGE_BUCKET,
    }


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
        debug=False
    )

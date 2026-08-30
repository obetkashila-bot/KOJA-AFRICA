import os
import json
import uuid
import secrets
import mimetypes
from datetime import datetime, timezone
from functools import wraps
from html import escape

import requests
from flask import (
    Flask,
    request,
    redirect,
    url_for,
    session,
    render_template_string,
    flash,
    abort,
    send_file,
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename


# ============================================================
# KOJA AFRICA
# Your Request • KOJA Handles It • You Receive the Result
#
# PRODUCTION ARCHITECTURE
# Flask + Supabase PostgreSQL REST API + Supabase Storage
#
# Render:
# Build:
#     pip install -r requirements.txt
#
# Start:
#     gunicorn app:app
#
# REQUIRED ENVIRONMENT VARIABLES:
#
# SUPABASE_URL
# SUPABASE_SERVICE_KEY
# SECRET_KEY
# ADMIN_EMAIL
# ADMIN_PASSWORD
#
# OPTIONAL:
# KOJA_STORAGE_BUCKET=koja-files
# MAX_FILE_MB=10
# ============================================================


# ============================================================
# APP CONFIGURATION
# ============================================================

app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    secrets.token_hex(32)
)

MAX_FILE_MB = int(os.environ.get("MAX_FILE_MB", "10"))
MAX_CONTENT_LENGTH = MAX_FILE_MB * 1024 * 1024

app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "").strip()

STORAGE_BUCKET = os.environ.get(
    "KOJA_STORAGE_BUCKET",
    "koja-files"
).strip()

ADMIN_EMAIL = os.environ.get(
    "ADMIN_EMAIL",
    "admin@koja-africa.com"
).strip().lower()

ADMIN_PASSWORD = os.environ.get(
    "ADMIN_PASSWORD",
    "CHANGE-THIS-ADMIN-PASSWORD"
)

SUPABASE_TIMEOUT = 30


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

ALLOWED_EXTENSIONS = {
    "pdf",
    "png",
    "jpg",
    "jpeg",
    "webp",
    "doc",
    "docx",
}

ALLOWED_MIME_TYPES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/webp",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

STATUSES = [
    "Request Received",
    "Processing",
    "Awaiting Client",
    "Completed",
    "Rejected",
]

SERVICE_LIST = [
    (
        "assignments",
        "📚 Assignments",
        "Send an assignment question or academic task to KOJA and receive the completed response.",
    ),
    (
        "university",
        "🎓 University Applications",
        "Get assistance with university applications, programme selection and application documents.",
    ),
    (
        "verification",
        "📄 Result Verification & Certification",
        "Submit your academic result or certificate for verification and certification assistance.",
    ),
    (
        "farmer",
        "🧑‍🌾 Farmer Registration",
        "Submit your farmer registration information through a guided registration process.",
    ),
    (
        "tpn",
        "📋 TPN Centre",
        "Get assistance with TPIN registration, updates, certificates and related TPN services.",
    ),
    (
        "materials",
        "📖 Higher Education Materials",
        "Request university-level notes, study materials, past papers and other learning resources.",
    ),
]

SERVICE_NAMES = dict(
    (key, name.replace("📚 ", "")
                .replace("🎓 ", "")
                .replace("📄 ", "")
                .replace("🧑‍🌾 ", "")
                .replace("📋 ", "")
                .replace("📖 ", ""))
    for key, name, desc in SERVICE_LIST
)


# ============================================================
# BASIC HELPERS
# ============================================================

def now_iso():
    return datetime.now(timezone.utc).isoformat()


def new_request_no():
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    token = secrets.token_hex(4).upper()
    return f"KOJA-{stamp}-{token}"


def service_name(service_type):
    return SERVICE_NAMES.get(
        service_type,
        "KOJA Service"
    )


def allowed_file(filename):
    if not filename:
        return False

    filename = secure_filename(filename)

    if "." not in filename:
        return False

    ext = filename.rsplit(".", 1)[1].lower()

    return ext in ALLOWED_EXTENSIONS


def get_extension(filename):
    filename = secure_filename(filename)

    if "." not in filename:
        return ""

    return filename.rsplit(".", 1)[1].lower()


def clean_required(name, label=None):
    value = request.form.get(name, "").strip()

    if not value:
        raise ValueError(
            f"{label or name.replace('_', ' ').title()} is required."
        )

    return value


def form_value(name):
    return request.form.get(name, "").strip()


def e(value):
    return escape(str(value or ""))


def json_dumps(data):
    return json.dumps(
        data,
        ensure_ascii=False
    )


def json_loads(value):
    try:
        return json.loads(value or "{}")
    except Exception:
        return {}


def status_class(status):
    mapping = {
        "Completed": "completed",
        "Processing": "processing",
        "Rejected": "rejected",
        "Awaiting Client": "awaiting",
        "Request Received": "received",
    }

    return mapping.get(status, "received")


# ============================================================
# SUPABASE
# ============================================================

def ensure_supabase_config():
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_SERVICE_KEY are not configured."
        )


def supabase_headers(extra=None):
    ensure_supabase_config()

    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
    }

    if extra:
        headers.update(extra)

    return headers


def supabase_request(
    method,
    endpoint,
    params=None,
    payload=None,
    headers=None,
    timeout=SUPABASE_TIMEOUT,
):
    ensure_supabase_config()

    url = f"{SUPABASE_URL}{endpoint}"

    request_headers = supabase_headers()

    if headers:
        request_headers.update(headers)

    response = requests.request(
        method,
        url,
        params=params,
        json=payload,
        headers=request_headers,
        timeout=timeout,
    )

    if not response.ok:
        message = response.text[:1000]

        raise RuntimeError(
            f"Supabase {method} {endpoint} failed "
            f"({response.status_code}): {message}"
        )

    if not response.text:
        return None

    try:
        return response.json()
    except Exception:
        return response.text


# ============================================================
# SUPABASE DATABASE HELPERS
# ============================================================

def db_select(
    table,
    params=None,
):
    return supabase_request(
        "GET",
        f"/rest/v1/{table}",
        params=params or {},
    )


def db_insert(
    table,
    data,
    select="*",
):
    return supabase_request(
        "POST",
        f"/rest/v1/{table}",
        params={
            "select": select
        },
        payload=data,
        headers={
            "Prefer": "return=representation"
        },
    )


def db_update(
    table,
    filters,
    data,
    select="*",
):
    params = dict(filters or {})
    params["select"] = select

    return supabase_request(
        "PATCH",
        f"/rest/v1/{table}",
        params=params,
        payload=data,
        headers={
            "Prefer": "return=representation"
        },
    )


def db_delete(
    table,
    filters,
):
    return supabase_request(
        "DELETE",
        f"/rest/v1/{table}",
        params=filters or {},
        headers={
            "Prefer": "return=minimal"
        },
    )


# ============================================================
# USER DATABASE
# ============================================================

def get_user_by_id(user_id):
    rows = db_select(
        "koja_users",
        {
            "id": f"eq.{user_id}",
            "limit": "1",
        }
    )

    return rows[0] if rows else None


def get_user_by_email(email):
    rows = db_select(
        "koja_users",
        {
            "email": f"eq.{email.lower()}",
            "limit": "1",
        }
    )

    return rows[0] if rows else None


def current_user():
    user_id = session.get("user_id")

    if not user_id:
        return None

    try:
        return get_user_by_id(user_id)
    except Exception:
        return None


# ============================================================
# AUTH DECORATORS
# ============================================================

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            flash(
                "Please create an account or log in first.",
                "error"
            )
            return redirect(url_for("login"))

        return view(*args, **kwargs)

    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return redirect(url_for("admin_login"))

        return view(*args, **kwargs)

    return wrapped


# ============================================================
# NOTIFICATIONS
# ============================================================

def add_notification(
    user_id,
    title,
    message,
):
    db_insert(
        "koja_notifications",
        {
            "user_id": user_id,
            "title": title,
            "message": message,
            "is_read": False,
            "created_at": now_iso(),
        }
    )


# ============================================================
# STORAGE
# ============================================================

def storage_upload(
    file_storage,
    folder,
    request_id,
):
    if not file_storage:
        return None

    original = secure_filename(
        file_storage.filename or ""
    )

    if not original:
        return None

    if not allowed_file(original):
        raise ValueError(
            "Unsupported file type. Use PDF, Word, JPG, PNG or WEBP."
        )

    ext = get_extension(original)

    if not ext:
        raise ValueError(
            "The uploaded file has no valid extension."
        )

    stored = (
        f"{folder}/"
        f"{request_id}/"
        f"{uuid.uuid4().hex}.{ext}"
    )

    content_type = (
        file_storage.mimetype
        or mimetypes.guess_type(original)[0]
        or "application/octet-stream"
    )

    if content_type not in ALLOWED_MIME_TYPES:
        raise ValueError(
            "The uploaded file type is not supported."
        )

    file_storage.stream.seek(0)

    data = file_storage.read()

    if not data:
        raise ValueError(
            "The uploaded file is empty."
        )

    if len(data) > MAX_CONTENT_LENGTH:
        raise ValueError(
            f"File is too large. Maximum size is {MAX_FILE_MB} MB."
        )

    url = (
        f"{SUPABASE_URL}"
        f"/storage/v1/object/"
        f"{STORAGE_BUCKET}/"
        f"{stored}"
    )

    response = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
            "apikey": SUPABASE_SERVICE_KEY,
            "Content-Type": content_type,
            "x-upsert": "false",
        },
        data=data,
        timeout=60,
    )

    if not response.ok:
        raise RuntimeError(
            "Supabase Storage upload failed: "
            + response.text[:1000]
        )

    return {
        "stored_path": stored,
        "original_name": original,
        "file_type": ext,
        "mime_type": content_type,
        "file_size": len(data),
    }


def storage_download(path):
    url = (
        f"{SUPABASE_URL}"
        f"/storage/v1/object/"
        f"{STORAGE_BUCKET}/"
        f"{path}"
    )

    response = requests.get(
        url,
        headers={
            "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
            "apikey": SUPABASE_SERVICE_KEY,
        },
        timeout=60,
    )

    if not response.ok:
        raise RuntimeError(
            "Unable to retrieve the requested file."
        )

    return response


def storage_delete(path):
    if not path:
        return

    url = (
        f"{SUPABASE_URL}"
        f"/storage/v1/object/"
        f"{STORAGE_BUCKET}"
    )

    requests.delete(
        url,
        headers={
            "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
            "apikey": SUPABASE_SERVICE_KEY,
            "Content-Type": "application/json",
        },
        json={
            "prefixes": [path]
        },
        timeout=30,
    )


def save_request_file(
    request_id,
    user_id,
    file_storage,
    category="client",
):
    uploaded = storage_upload(
        file_storage,
        category,
        str(request_id),
    )

    if not uploaded:
        return None

    row = db_insert(
        "koja_request_files",
        {
            "request_id": request_id,
            "uploaded_by": user_id,
            "original_name": uploaded["original_name"],
            "stored_path": uploaded["stored_path"],
            "file_type": uploaded["file_type"],
            "mime_type": uploaded["mime_type"],
            "file_size": uploaded["file_size"],
            "category": category,
            "created_at": now_iso(),
        }
    )

    return row[0] if row else None


# ============================================================
# REQUEST DATABASE
# ============================================================

def get_request(request_id):
    rows = db_select(
        "koja_requests",
        {
            "id": f"eq.{request_id}",
            "limit": "1",
        }
    )

    if not rows:
        return None

    row = rows[0]

    users = db_select(
        "koja_users",
        {
            "id": f"eq.{row['user_id']}",
            "limit": "1",
        }
    )

    if users:
        user = users[0]

        row["full_name"] = user.get("full_name", "")
        row["user_email"] = user.get("email", "")
        row["user_phone"] = user.get("phone", "")

    else:
        row["full_name"] = ""
        row["user_email"] = ""
        row["user_phone"] = ""

    return row


def get_request_files(request_id):
    return db_select(
        "koja_request_files",
        {
            "request_id": f"eq.{request_id}",
            "order": "created_at.desc",
        }
    )


def create_request(
    user_id,
    service_type,
    data,
):
    request_no = new_request_no()
    timestamp = now_iso()

    row = db_insert(
        "koja_requests",
        {
            "request_no": request_no,
            "user_id": user_id,
            "service_type": service_type,
            "service_name": service_name(service_type),
            "status": "Request Received",
            "data_json": json_dumps(data),
            "admin_response": None,
            "output_file": None,
            "output_file_original": None,
            "created_at": timestamp,
            "updated_at": timestamp,
        }
    )

    if not row:
        raise RuntimeError(
            "The request could not be created."
        )

    request_id = row[0]["id"]

    add_notification(
        user_id,
        "Request Received",
        (
            f"Your {service_name(service_type)} request "
            f"{request_no} has been received by KOJA."
        )
    )

    return request_id, request_no


def parse_request_data(row):
    return json_loads(
        row.get("data_json", "{}")
    )


# ============================================================
# HTML DESIGN
# ============================================================

CSS = """
:root {
    --green: #19733f;
    --green-dark: #12552f;
    --blue: #214f91;
    --gold: #e7b73c;
    --bg: #f4f7f5;
    --card: #ffffff;
    --text: #18212b;
    --muted: #667085;
    --border: #dfe5e1;
    --danger: #b42318;
    --success: #027a48;
}

* {
    box-sizing: border-box;
}

body {
    margin: 0;
    font-family:
        Inter,
        -apple-system,
        BlinkMacSystemFont,
        "Segoe UI",
        sans-serif;
    background: var(--bg);
    color: var(--text);
    line-height: 1.55;
}

a {
    color: var(--green);
    text-decoration: none;
}

a:hover {
    text-decoration: underline;
}

nav {
    background: #ffffff;
    border-bottom: 1px solid var(--border);
    position: sticky;
    top: 0;
    z-index: 10;
}

.nav-inner {
    max-width: 1180px;
    margin: auto;
    padding: 14px 18px;
    display: flex;
    gap: 12px;
    align-items: center;
    justify-content: space-between;
}

.logo {
    font-weight: 900;
    font-size: 20px;
    color: var(--green);
}

.nav-links {
    display: flex;
    flex-wrap: wrap;
    gap: 7px;
    justify-content: flex-end;
}

.nav-links a {
    padding: 8px 11px;
    border-radius: 9px;
    font-size: 14px;
}

.nav-links a:hover {
    background: #edf6f0;
    text-decoration: none;
}

.container {
    max-width: 1180px;
    margin: auto;
    padding: 24px 16px 70px;
}

.hero {
    background:
        linear-gradient(
            135deg,
            #ffffff,
            #eef8f1
        );
    border: 1px solid var(--border);
    border-radius: 20px;
    padding: 38px 28px;
    margin-bottom: 22px;
}

.hero h1 {
    margin-top: 0;
    font-size: clamp(30px, 6vw, 50px);
    line-height: 1.1;
}

.hero p {
    font-size: 18px;
    color: var(--muted);
    max-width: 760px;
}

.card {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 16px;
    padding: 22px;
    margin-bottom: 18px;
    box-shadow:
        0 4px 18px rgba(20, 40, 30, .04);
}

.card h2 {
    margin-top: 0;
}

.grid {
    display: grid;
    grid-template-columns:
        repeat(
            auto-fit,
            minmax(230px, 1fr)
        );
    gap: 16px;
}

.grid2 {
    display: grid;
    grid-template-columns:
        repeat(
            auto-fit,
            minmax(300px, 1fr)
        );
    gap: 18px;
}

.grid3 {
    display: grid;
    grid-template-columns:
        repeat(
            auto-fit,
            minmax(180px, 1fr)
        );
    gap: 14px;
}

.service {
    background: #ffffff;
    border: 1px solid var(--border);
    border-radius: 15px;
    padding: 20px;
}

.service:hover {
    border-color: #a7cbb4;
}

.service h3 {
    margin-top: 0;
}

.service p {
    color: var(--muted);
}

.service-icon {
    font-size: 34px;
    margin-bottom: 8px;
}

.field {
    margin-bottom: 16px;
}

label {
    display: block;
    font-weight: 700;
    margin-bottom: 7px;
}

input,
select,
textarea {
    width: 100%;
    padding: 12px 13px;
    border: 1px solid #cfd8d2;
    border-radius: 9px;
    background: white;
    font: inherit;
}

textarea {
    min-height: 130px;
    resize: vertical;
}

input:focus,
select:focus,
textarea:focus {
    outline: 2px solid rgba(25, 115, 63, .16);
    border-color: var(--green);
}

.btn {
    display: inline-block;
    border: 0;
    border-radius: 9px;
    padding: 11px 17px;
    background: var(--blue);
    color: white;
    font-weight: 700;
    cursor: pointer;
    text-decoration: none;
}

.btn:hover {
    text-decoration: none;
    opacity: .92;
}

.btn.green {
    background: var(--green);
}

.btn.light {
    background: #edf1ef;
    color: var(--text);
}

.btn.danger {
    background: var(--danger);
}

.actions {
    display: flex;
    flex-wrap: wrap;
    gap: 9px;
    margin-top: 18px;
}

.alert {
    max-width: 1180px;
    margin: 14px auto;
    padding: 13px 16px;
    border-radius: 10px;
    font-weight: 600;
}

.alert.error {
    background: #fef3f2;
    color: #b42318;
    border: 1px solid #fecdca;
}

.alert.success {
    background: #ecfdf3;
    color: #027a48;
    border: 1px solid #abefc6;
}

.alert.warning {
    background: #fffaeb;
    color: #b54708;
    border: 1px solid #fedf89;
}

.small,
.help {
    color: var(--muted);
    font-size: 13px;
}

.filebox {
    background: #f8faf9;
    padding: 14px;
    border-radius: 10px;
    border: 1px dashed #bccbc1;
}

.data-table {
    width: 100%;
    border-collapse: collapse;
}

.data-table th,
.data-table td {
    padding: 11px 9px;
    border-bottom: 1px solid var(--border);
    text-align: left;
    vertical-align: top;
}

.data-table th {
    background: #f7f9f8;
}

.status {
    display: inline-block;
    padding: 5px 9px;
    border-radius: 999px;
    font-size: 12px;
    font-weight: 800;
}

.status.received {
    background: #eef4ff;
    color: #175cd3;
}

.status.processing {
    background: #fff6ed;
    color: #b54708;
}

.status.awaiting {
    background: #f4f3ff;
    color: #5925dc;
}

.status.completed {
    background: #ecfdf3;
    color: #027a48;
}

.status.rejected {
    background: #fef3f2;
    color: #b42318;
}

.kv {
    display: grid;
    grid-template-columns:
        minmax(150px, 240px)
        1fr;
    border: 1px solid var(--border);
    border-radius: 10px;
    overflow: hidden;
}

.kv > div {
    padding: 10px 12px;
    border-bottom: 1px solid var(--border);
}

.kv .k {
    font-weight: 700;
    background: #f8faf9;
}

.stepbar {
    display: flex;
    gap: 12px;
    margin: 20px 0;
}

.step {
    width: 38px;
    height: 38px;
    display: grid;
    place-items: center;
    border-radius: 50%;
    background: #e5e9e6;
    font-weight: 800;
}

.step.active {
    background: var(--green);
    color: white;
}

.step.done {
    background: #d8f0df;
    color: var(--green-dark);
}

footer {
    border-top: 1px solid var(--border);
    background: white;
    padding: 24px 16px;
    text-align: center;
    color: var(--muted);
}

@media (max-width: 720px) {
    .nav-inner {
        align-items: flex-start;
        flex-direction: column;
    }

    .nav-links {
        justify-content: flex-start;
    }

    .container {
        padding: 16px 10px 50px;
    }

    .hero {
        padding: 26px 18px;
    }

    .card {
        padding: 17px;
    }

    .data-table {
        display: block;
        overflow-x: auto;
        white-space: nowrap;
    }

    .kv {
        grid-template-columns: 1fr;
    }
}
"""


# ============================================================
# PAGE RENDERER
# ============================================================

def page(
    title,
    body,
    admin=False,
):
    user = current_user()

    if admin:
        nav = """
        <nav>
          <div class="nav-inner">
            <div class="logo">KOJA AFRICA — ADMIN</div>
            <div class="nav-links">
              <a href="/admin">Dashboard</a>
              <a href="/admin/logout">Logout</a>
            </div>
          </div>
        </nav>
        """

    elif user:
        nav = """
        <nav>
          <div class="nav-inner">
            <div class="logo">KOJA AFRICA</div>
            <div class="nav-links">
              <a href="/dashboard">Home</a>
              <a href="/services">Services</a>
              <a href="/my-requests">My Requests</a>
              <a href="/notifications">Notifications</a>
              <a href="/profile">Profile</a>
              <a href="/logout">Logout</a>
            </div>
          </div>
        </nav>
        """

    else:
        nav = """
        <nav>
          <div class="nav-inner">
            <div class="logo">KOJA AFRICA</div>
            <div class="nav-links">
              <a href="/">Home</a>
              <a href="/login">Client Login</a>
              <a href="/register">Create Account</a>
            </div>
          </div>
        </nav>
        """

    from flask import get_flashed_messages

    flashes = ""

    for category, message in get_flashed_messages(
        with_categories=True
    ):
        flashes += (
            f'<div class="alert {e(category)}">'
            f'{e(message)}'
            f'</div>'
        )

    template = """
    <!doctype html>
    <html lang="en">
    <head>
      <meta charset="utf-8">
      <meta
        name="viewport"
        content="width=device-width, initial-scale=1"
      >
      <meta
        name="description"
        content="KOJA AFRICA - Your Request, KOJA Handles It, You Receive the Result"
      >
      <title>{{ title }} | KOJA AFRICA</title>
      <style>
        {{ css|safe }}
      </style>
    </head>

    <body>

      {{ nav|safe }}

      {{ flashes|safe }}

      <main class="container">
        {{ body|safe }}
      </main>

      <footer>
        <strong>KOJA AFRICA</strong><br>
        Your Request • KOJA Handles It • You Receive the Result
      </footer>

    </body>
    </html>
    """

    return render_template_string(
        template,
        title=title,
        css=CSS,
        nav=nav,
        flashes=flashes,
        body=body,
    )


# ============================================================
# HOME
# ============================================================

@app.route("/")
def home():
    cards = ""

    for key, name, desc in SERVICE_LIST:
        cards += f"""
        <div class="service">
          <div class="service-icon">
            {e(name.split(" ", 1)[0])}
          </div>

          <h3>{e(name)}</h3>

          <p>{e(desc)}</p>

          <a class="btn green"
             href="/services/{e(key)}">
             Choose Service →
          </a>
        </div>
        """

    body = f"""
    <section class="hero">
      <h1>KOJA AFRICA</h1>

      <p>
        <strong>Your Request • KOJA Handles It • You Receive the Result</strong>
      </p>

      <p>
        KOJA AFRICA provides a central online service platform
        for academic, application, registration, verification
        and education-support requests.
      </p>

      <div class="actions">
        <a class="btn green" href="/register">
          Create Account
        </a>

        <a class="btn light" href="/login">
          Client Login
        </a>
      </div>
    </section>

    <section class="card">
      <h2>How KOJA Works</h2>

      <div class="grid3">
        <div class="service">
          <h3>1. Choose</h3>
          <p>
            Select the KOJA service you need.
          </p>
        </div>

        <div class="service">
          <h3>2. Send</h3>
          <p>
            Complete the appropriate form and
            upload supporting documents.
          </p>
        </div>

        <div class="service">
          <h3>3. KOJA Handles It</h3>
          <p>
            Your request is received and processed
            by the KOJA administration team.
          </p>
        </div>

        <div class="service">
          <h3>4. Receive</h3>
          <p>
            Follow the request status and receive
            the completed response or document.
          </p>
        </div>
      </div>
    </section>

    <section class="card">
      <h2>KOJA Services</h2>

      <div class="grid3">
        {cards}
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
        full_name = form_value("full_name")
        email = form_value("email").lower()
        phone = form_value("phone")
        password = request.form.get("password", "")
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
                "Password must be at least 6 characters.",
                "error"
            )

        else:
            try:
                existing = get_user_by_email(email)

                if existing:
                    flash(
                        "That email is already registered.",
                        "error"
                    )
                else:
                    row = db_insert(
                        "koja_users",
                        {
                            "full_name": full_name,
                            "email": email,
                            "phone": phone,
                            "password_hash":
                                generate_password_hash(
                                    password
                                ),
                            "created_at": now_iso(),
                        }
                    )

                    if row:
                        flash(
                            "Account created successfully. "
                            "You can now log in.",
                            "success"
                        )

                        return redirect(
                            url_for("login")
                        )

            except Exception as exc:
                flash(
                    f"Account creation failed: {exc}",
                    "error"
                )

    body = """
    <div class="card">
      <h2>Create KOJA Account</h2>

      <p class="small">
        Create an account to submit requests and
        track your KOJA services.
      </p>

      <form method="post">

        <div class="grid">

          <div class="field">
            <label>Full Name *</label>
            <input
              name="full_name"
              required
              autocomplete="name"
            >
          </div>

          <div class="field">
            <label>Phone</label>
            <input
              name="phone"
              autocomplete="tel"
            >
          </div>

          <div class="field">
            <label>Email *</label>
            <input
              type="email"
              name="email"
              required
              autocomplete="email"
            >
          </div>

          <div class="field">
            <label>Password *</label>
            <input
              type="password"
              name="password"
              minlength="6"
              required
              autocomplete="new-password"
            >
          </div>

          <div class="field">
            <label>Confirm Password *</label>
            <input
              type="password"
              name="confirm_password"
              minlength="6"
              required
              autocomplete="new-password"
            >
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
        email = form_value("email").lower()
        password = request.form.get(
            "password",
            ""
        )

        try:
            user = get_user_by_email(email)

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

            flash(
                "Invalid email or password.",
                "error"
            )

        except Exception as exc:
            flash(
                f"Login failed: {exc}",
                "error"
            )

    body = """
    <div class="card"
         style="max-width:600px;margin:auto">

      <h2>Client Login</h2>

      <form method="post">

        <div class="field">
          <label>Email *</label>
          <input
            type="email"
            name="email"
            required
            autocomplete="email"
          >
        </div>

        <div class="field">
          <label>Password *</label>
          <input
            type="password"
            name="password"
            required
            autocomplete="current-password"
          >
        </div>

        <button class="btn green">
          Login
        </button>

      </form>

      <div class="actions">
        <a
          href="/register"
          class="btn light"
        >
          Create Account
        </a>
      </div>

    </div>
    """

    return page(
        "Client Login",
        body
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
# CLIENT DASHBOARD
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
        "koja_requests",
        {
            "user_id": f"eq.{user['id']}",
            "order": "created_at.desc",
            "limit": "5",
        }
    )

    counts = {}

    for status in STATUSES:
        result = db_select(
            "koja_requests",
            {
                "user_id": f"eq.{user['id']}",
                "status": f"eq.{status}",
                "select": "id",
            }
        )

        counts[status] = len(result)

    cards = ""

    for status, value in counts.items():
        cards += f"""
        <div class="service">
          <strong>{e(status)}</strong>
          <div style="font-size:30px;margin-top:8px">
            {value}
          </div>
        </div>
        """

    table_rows = ""

    for row in rows:
        cls = status_class(
            row["status"]
        )

        table_rows += f"""
        <tr>
          <td>
            <a href="/request/{row['id']}">
              <strong>
                {e(row['request_no'])}
              </strong>
            </a>
          </td>

          <td>
            {e(row['service_name'])}
          </td>

          <td>
            <span class="status {cls}">
              {e(row['status'])}
            </span>
          </td>

          <td>
            {e(str(row['created_at'])[:10])}
          </td>
        </tr>
        """

    body = f"""
    <section class="hero">
      <h1>
        Welcome, {e(user['full_name'])}
      </h1>

      <p>
        Choose a service, send your request,
        let KOJA handle it and receive the result.
      </p>

      <a
        class="btn green"
        href="/services"
      >
        Explore KOJA Services
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
          <th>Date</th>
        </tr>

        {table_rows or
        '<tr><td colspan="4">No requests yet.</td></tr>'}
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

    for key, name, desc in SERVICE_LIST:
        cards += f"""
        <div class="service">
          <div class="service-icon">
            {e(name.split(" ", 1)[0])}
          </div>

          <h3>{e(name)}</h3>

          <p>{e(desc)}</p>

          <a
            class="btn green"
            href="/services/{e(key)}"
          >
            Choose Service
          </a>
        </div>
        """

    body = f"""
    <section class="card">
      <h2>KOJA Services</h2>

      <p>
        Choose the service you need.
        Each service has its own dedicated workflow.
      </p>

      <div class="grid3">
        {cards}
      </div>
    </section>
    """

    return page(
        "KOJA Services",
        body
    )


# ============================================================
# SERVICE ROUTER
# ============================================================

@app.route(
    "/services/<service_type>"
)
@login_required
def service_router(service_type):
    routes = {
        "assignments": "assignment_request",
        "university": "university_application",
        "verification": "verification_request",
        "farmer": "farmer_step1",
        "tpn": "tpn_request",
        "materials": "materials_request",
    }

    endpoint = routes.get(service_type)

    if not endpoint:
        abort(404)

    return redirect(
        url_for(endpoint)
    )


# ============================================================
# ASSIGNMENTS
# ============================================================

@app.route(
    "/request/assignments",
    methods=["GET", "POST"]
)
@login_required
def assignment_request():
    if request.method == "POST":
        try:
            data = {
                "institution": clean_required(
                    "institution",
                    "Institution"
                ),
                "programme": clean_required(
                    "programme",
                    "Programme"
                ),
                "course": clean_required(
                    "course",
                    "Course / Subject"
                ),
                "assignment_title": clean_required(
                    "assignment_title",
                    "Assignment title"
                ),
                "deadline": form_value(
                    "deadline"
                ),
                "academic_level": form_value(
                    "academic_level"
                ),
                "question": clean_required(
                    "question",
                    "Assignment question"
                ),
                "instructions": form_value(
                    "instructions"
                ),
            }

            user = current_user()

            request_id, request_no = create_request(
                user["id"],
                "assignments",
                data
            )

            files = request.files.getlist(
                "supporting_documents"
            )

            for uploaded in files:
                if uploaded and uploaded.filename:
                    save_request_file(
                        request_id,
                        user["id"],
                        uploaded,
                        "assignment"
                    )

            flash(
                f"Assignment request {request_no} "
                "was submitted successfully.",
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
            flash(
                f"Assignment submission failed: {exc}",
                "error"
            )

    body = """
    <div class="card">
      <h2>📚 Assignments</h2>

      <p>
        Submit your assignment question to KOJA.
        You can attach the assignment paper,
        instructions or supporting material.
      </p>

      <form
        method="post"
        enctype="multipart/form-data"
      >

        <div class="grid">

          <div class="field">
            <label>Institution *</label>
            <input name="institution" required>
          </div>

          <div class="field">
            <label>Programme *</label>
            <input name="programme" required>
          </div>

          <div class="field">
            <label>Course / Subject *</label>
            <input name="course" required>
          </div>

          <div class="field">
            <label>Academic Level</label>
            <input name="academic_level">
          </div>

          <div class="field">
            <label>Assignment Title *</label>
            <input name="assignment_title" required>
          </div>

          <div class="field">
            <label>Deadline</label>
            <input
              type="date"
              name="deadline"
            >
          </div>

        </div>

        <div class="field">
          <label>Assignment Question *</label>
          <textarea
            name="question"
            required
            placeholder="Paste or type the assignment question here."
          ></textarea>
        </div>

        <div class="field">
          <label>Instructions / Requirements</label>
          <textarea
            name="instructions"
            placeholder="Explain the required format, number of pages, referencing style, etc."
          ></textarea>
        </div>

        <div class="field filebox">
          <label>Supporting Files</label>

          <input
            type="file"
            name="supporting_documents"
            multiple
            accept=".pdf,.doc,.docx,.jpg,.jpeg,.png,.webp"
          >

          <div class="help">
            Maximum file size:
            10 MB per file.
          </div>
        </div>

        <button class="btn green">
          Send Assignment to KOJA
        </button>

      </form>
    </div>
    """

    return page(
        "Assignments",
        body
    )


# ============================================================
# UNIVERSITY APPLICATION
# ============================================================

@app.route(
    "/request/university",
    methods=["GET", "POST"]
)
@login_required
def university_application():
    if request.method == "POST":
        try:
            data = {
                "university": clean_required(
                    "university",
                    "University"
                ),
                "programme": clean_required(
                    "programme",
                    "Programme"
                ),
                "application_type": clean_required(
                    "application_type",
                    "Application type"
                ),
                "intake": form_value(
                    "intake"
                ),
                "applicant_full_name": clean_required(
                    "applicant_full_name",
                    "Applicant full name"
                ),
                "nrc_number": clean_required(
                    "nrc_number",
                    "NRC number"
                ),
                "date_of_birth": clean_required(
                    "date_of_birth",
                    "Date of birth"
                ),
                "gender": clean_required(
                    "gender",
                    "Gender"
                ),
                "phone": clean_required(
                    "phone",
                    "Phone"
                ),
                "email": clean_required(
                    "email",
                    "Email"
                ),
                "province": clean_required(
                    "province",
                    "Province"
                ),
                "district": clean_required(
                    "district",
                    "District"
                ),
                "qualifications": clean_required(
                    "qualifications",
                    "Previous qualifications"
                ),
                "additional_information": form_value(
                    "additional_information"
                ),
            }

            user = current_user()

            request_id, request_no = create_request(
                user["id"],
                "university",
                data
            )

            files = request.files.getlist(
                "documents"
            )

            for uploaded in files:
                if uploaded and uploaded.filename:
                    save_request_file(
                        request_id,
                        user["id"],
                        uploaded,
                        "university"
                    )

            flash(
                f"University application request "
                f"{request_no} was submitted.",
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
            flash(
                f"University application failed: {exc}",
                "error"
            )

    province_options = "".join(
        f"<option>{e(p)}</option>"
        for p in PROVINCES
    )

    gender_options = "".join(
        f"<option>{e(g)}</option>"
        for g in GENDERS
    )

    body = f"""
    <div class="card">
      <h2>🎓 University Applications</h2>

      <p>
        Submit your university application
        information and supporting documents
        to KOJA.
      </p>

      <form
        method="post"
        enctype="multipart/form-data"
      >

        <div class="grid">

          <div class="field">
            <label>University *</label>
            <input name="university" required>
          </div>

          <div class="field">
            <label>Programme *</label>
            <input name="programme" required>
          </div>

          <div class="field">
            <label>Application Type *</label>

            <select name="application_type" required>
              <option value="">
                Select application type
              </option>
              <option>
                Undergraduate Application
              </option>
              <option>
                Postgraduate Application
              </option>
              <option>
                Application Assistance
              </option>
              <option>
                Transfer Application
              </option>
              <option>
                Other
              </option>
            </select>
          </div>

          <div class="field">
            <label>Intake</label>
            <input
              name="intake"
              placeholder="e.g. January 2027"
            >
          </div>

          <div class="field">
            <label>Applicant Full Name *</label>
            <input
              name="applicant_full_name"
              required
            >
          </div>

          <div class="field">
            <label>NRC Number *</label>
            <input
              name="nrc_number"
              required
            >
          </div>

          <div class="field">
            <label>Date of Birth *</label>
            <input
              type="date"
              name="date_of_birth"
              required
            >
          </div>

          <div class="field">
            <label>Gender *</label>
            <select name="gender" required>
              <option value="">
                Select gender
              </option>
              {gender_options}
            </select>
          </div>

          <div class="field">
            <label>Phone *</label>
            <input
              name="phone"
              required
            >
          </div>

          <div class="field">
            <label>Email *</label>
            <input
              type="email"
              name="email"
              required
            >
          </div>

          <div class="field">
            <label>Province *</label>
            <select name="province" required>
              <option value="">
                Select province
              </option>
              {province_options}
            </select>
          </div>

          <div class="field">
            <label>District *</label>
            <input
              name="district"
              required
            >
          </div>

        </div>

        <div class="field">
          <label>
            Previous Qualifications *
          </label>

          <textarea
            name="qualifications"
            required
            placeholder="Enter your qualifications, school, examination results, etc."
          ></textarea>
        </div>

        <div class="field">
          <label>
            Additional Information
          </label>

          <textarea
            name="additional_information"
          ></textarea>
        </div>

        <div class="field filebox">
          <label>Application Documents</label>

          <input
            type="file"
            name="documents"
            multiple
            accept=".pdf,.doc,.docx,.jpg,.jpeg,.png,.webp"
          >

          <div class="help">
            You may attach certificates,
            NRC, passport photo, transcripts
            and other relevant documents.
          </div>
        </div>

        <button class="btn green">
          Send University Application
        </button>

      </form>
    </div>
    """

    return page(
        "University Applications",
        body
    )


# ============================================================
# RESULT VERIFICATION
# ============================================================

@app.route(
    "/request/verification",
    methods=["GET", "POST"]
)
@login_required
def verification_request():
    if request.method == "POST":
        try:
            data = {
                "full_name": clean_required(
                    "full_name",
                    "Full name"
                ),
                "nrc_number": clean_required(
                    "nrc_number",
                    "NRC number"
                ),
                "phone": clean_required(
                    "phone",
                    "Phone"
                ),
                "email": clean_required(
                    "email",
                    "Email"
                ),
                "institution": clean_required(
                    "institution",
                    "Institution"
                ),
                "qualification": clean_required(
                    "qualification",
                    "Qualification"
                ),
                "programme": clean_required(
                    "programme",
                    "Programme"
                ),
                "graduation_year": clean_required(
                    "graduation_year",
                    "Graduation year"
                ),
                "verification_type": clean_required(
                    "verification_type",
                    "Verification type"
                ),
                "purpose": clean_required(
                    "purpose",
                    "Purpose"
                ),
                "additional_information": form_value(
                    "additional_information"
                ),
            }

            user = current_user()

            request_id, request_no = create_request(
                user["id"],
                "verification",
                data
            )

            files = request.files.getlist(
                "documents"
            )

            for uploaded in files:
                if uploaded and uploaded.filename:
                    save_request_file(
                        request_id,
                        user["id"],
                        uploaded,
                        "verification"
                    )

            flash(
                f"Verification request {request_no} "
                "was submitted.",
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
            flash(
                f"Verification request failed: {exc}",
                "error"
            )

    body = """
    <div class="card">

      <h2>
        📄 Result Verification & Certification
      </h2>

      <p>
        Provide the information KOJA needs
        to process your verification request.
      </p>

      <form
        method="post"
        enctype="multipart/form-data"
      >

        <div class="grid">

          <div class="field">
            <label>Full Name *</label>
            <input name="full_name" required>
          </div>

          <div class="field">
            <label>NRC Number *</label>
            <input name="nrc_number" required>
          </div>

          <div class="field">
            <label>Phone *</label>
            <input name="phone" required>
          </div>

          <div class="field">
            <label>Email *</label>
            <input
              type="email"
              name="email"
              required
            >
          </div>

          <div class="field">
            <label>Institution *</label>
            <input name="institution" required>
          </div>

          <div class="field">
            <label>Qualification *</label>
            <input name="qualification" required>
          </div>

          <div class="field">
            <label>Programme *</label>
            <input name="programme" required>
          </div>

          <div class="field">
            <label>Graduation Year *</label>
            <input
              name="graduation_year"
              required
            >
          </div>

          <div class="field">
            <label>Verification Type *</label>

            <select
              name="verification_type"
              required
            >
              <option value="">
                Select type
              </option>
              <option>
                Result Verification
              </option>
              <option>
                Certificate Verification
              </option>
              <option>
                Academic Certification
              </option>
              <option>
                Other Verification
              </option>
            </select>
          </div>

          <div class="field">
            <label>Purpose *</label>
            <input
              name="purpose"
              required
              placeholder="Employment, further studies, immigration, etc."
            >
          </div>

        </div>

        <div class="field">
          <label>Additional Information</label>
          <textarea
            name="additional_information"
          ></textarea>
        </div>

        <div class="field filebox">
          <label>Result / Certificate Documents *</label>

          <input
            type="file"
            name="documents"
            multiple
            required
            accept=".pdf,.doc,.docx,.jpg,.jpeg,.png,.webp"
          >

          <div class="help">
            Upload the result, certificate,
            transcript or supporting document.
          </div>
        </div>

        <button class="btn green">
          Send Verification Request
        </button>

      </form>
    </div>
    """

    return page(
        "Result Verification",
        body
    )


# ============================================================
# FARMER REGISTRATION - STEP 1
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
                "nrc": clean_required(
                    "nrc",
                    "NRC"
                ),
                "date_of_birth": clean_required(
                    "date_of_birth",
                    "Date of birth"
                ),
                "first_name": clean_required(
                    "first_name",
                    "First name"
                ),
                "middle_names": form_value(
                    "middle_names"
                ),
                "last_name": clean_required(
                    "last_name",
                    "Last name"
                ),
                "gender": clean_required(
                    "gender",
                    "Gender"
                ),
                "phone": clean_required(
                    "phone",
                    "Phone"
                ),
            }

            session["farmer_data"] = data

            return redirect(
                url_for("farmer_step2")
            )

        except ValueError as exc:
            flash(
                str(exc),
                "error"
            )

    body = """
    <div class="card">

      <h2 style="text-align:center">
        🧑‍🌾 Farmer Registration
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
            <input
              name="nrc"
              placeholder="123456/10/1"
              required
            >
          </div>

          <div class="field">
            <label>Date of Birth *</label>
            <input
              type="date"
              name="date_of_birth"
              required
            >
          </div>

          <div class="field">
            <label>First Name *</label>
            <input name="first_name" required>
          </div>

          <div class="field">
            <label>Middle Names</label>
            <input name="middle_names">
          </div>

          <div class="field">
            <label>Last Name *</label>
            <input name="last_name" required>
          </div>

          <div class="field">
            <label>Gender *</label>

            <select name="gender" required>
              <option value="">
                Select gender
              </option>
              <option>Male</option>
              <option>Female</option>
              <option>Other</option>
            </select>
          </div>

          <div class="field">
            <label>Phone *</label>
            <input name="phone" required>
          </div>

        </div>

        <button class="btn green">
          Continue to Location →
        </button>

      </form>
    </div>
    """

    return page(
        "Farmer Registration",
        body
    )


# ============================================================
# FARMER REGISTRATION - STEP 2
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
                "province": clean_required(
                    "province",
                    "Province"
                ),
                "district": clean_required(
                    "district",
                    "District"
                ),
                "constituency": form_value(
                    "constituency"
                ),
                "chiefdom": form_value(
                    "chiefdom"
                ),
                "farming_area": clean_required(
                    "farming_area",
                    "Farming location / area"
                ),
            })

            session["farmer_data"] = data

            return redirect(
                url_for("farmer_step3")
            )

        except ValueError as exc:
            flash(
                str(exc),
                "error"
            )

    province_options = "".join(
        f"<option>{e(p)}</option>"
        for p in PROVINCES
    )

    body = f"""
    <div class="card">

      <h2 style="text-align:center">
        🧑‍🌾 Farmer Registration
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

          <select name="province" required>
            <option value="">
              Select Province
            </option>
            {province_options}
          </select>
        </div>

        <div class="grid">

          <div class="field">
            <label>District *</label>
            <input name="district" required>
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
            <input
              name="farming_area"
              required
            >
          </div>

        </div>

        <div class="actions">

          <a
            class="btn light"
            href="/request/farmer"
          >
            ← Back
          </a>

          <button class="btn green">
            Continue to Payment →
          </button>

        </div>

      </form>
    </div>
    """

    return page(
        "Farmer Registration - Location",
        body
    )


# ============================================================
# FARMER REGISTRATION - STEP 3
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

            payment_method = clean_required(
                "payment_method",
                "Payment method"
            )

            provider = clean_required(
                "provider",
                "Provider"
            )

            account_no = clean_required(
                "account_no",
                "Account number"
            )

            account_name = clean_required(
                "account_name",
                "Account name"
            )

            data.update({
                "payment_method": payment_method,
                "provider": provider,
                "branch": form_value("branch"),
                "account_no": account_no,
                "account_name": account_name,
            })

            user = current_user()

            request_id, request_no = create_request(
                user["id"],
                "farmer",
                data
            )

            uploaded = request.files.get(
                "nrc_card"
            )

            if uploaded and uploaded.filename:
                save_request_file(
                    request_id,
                    user["id"],
                    uploaded,
                    "farmer"
                )

            session.pop(
                "farmer_data",
                None
            )

            flash(
                f"Farmer request {request_no} "
                "was submitted successfully.",
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
            flash(
                f"Farmer request failed: {exc}",
                "error"
            )

    body = f"""
    <div class="card">

      <h2 style="text-align:center">
        🧑‍🌾 Farmer Registration
      </h2>

      <div class="stepbar">
        <div class="step done">✓</div>
        <div class="step done">✓</div>
        <div class="step active">3</div>
      </div>

      <h2>Step 3: Payment & Submit</h2>

      <form
        method="post"
        enctype="multipart/form-data"
      >

        <div class="field">

          <label>Payment Method *</label>

          <select
            name="payment_method"
            id="payment_method"
            required
            onchange="updateProviders()"
          >
            <option value="">
              Select method
            </option>
            <option>Bank Account</option>
            <option>Mobile Money</option>
          </select>

        </div>

        <div class="field">

          <label>Provider *</label>

          <select
            name="provider"
            id="provider"
            required
          >
            <option value="">
              Select provider
            </option>
          </select>

        </div>

        <div class="field">

          <label>Branch</label>

          <input
            name="branch"
            placeholder="Bank branch, if applicable"
          >

        </div>

        <div class="grid">

          <div class="field">
            <label>Account No. *</label>
            <input
              name="account_no"
              required
            >
          </div>

          <div class="field">
            <label>Account Name *</label>
            <input
              name="account_name"
              required
            >
          </div>

        </div>

        <div class="field filebox">

          <label>
            NRC Card / Supporting Document
          </label>

          <input
            type="file"
            name="nrc_card"
            accept=".pdf,.jpg,.jpeg,.png,.webp,.doc,.docx"
          >

          <div class="help">
            Maximum {MAX_FILE_MB} MB.
          </div>

        </div>

        <div class="actions">

          <a
            class="btn light"
            href="/request/farmer/location"
          >
            ← Back
          </a>

          <button class="btn green">
            Submit Farmer Request
          </button>

        </div>

      </form>
    </div>

    <script>
      const banks = {json.dumps(BANKS)};
      const mobiles = {json.dumps(MOBILE_PROVIDERS)};

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

        if (method === "Bank Account") {{
          list = banks;
        }}

        if (method === "Mobile Money") {{
          list = mobiles;
        }}

        list.forEach(function(item) {{
          const option =
            document.createElement("option");

          option.value = item;
          option.textContent = item;

          provider.appendChild(option);
        }});
      }}
    </script>
    """

    return page(
        "Farmer Registration - Payment",
        body
    )


# ============================================================
# TPN CENTRE
# ============================================================

@app.route(
    "/request/tpn",
    methods=["GET", "POST"]
)
@login_required
def tpn_request():
    if request.method == "POST":
        try:
            data = {
                "nrc_number": clean_required(
                    "nrc_number",
                    "NRC number"
                ),
                "date_of_birth": clean_required(
                    "date_of_birth",
                    "Date of birth"
                ),
                "first_name": clean_required(
                    "first_name",
                    "First name"
                ),
                "middle_names": form_value(
                    "middle_names"
                ),
                "last_name": clean_required(
                    "last_name",
                    "Last name"
                ),
                "gender": clean_required(
                    "gender",
                    "Gender"
                ),
                "phone_number": clean_required(
                    "phone_number",
                    "Phone number"
                ),
                "email": clean_required(
                    "email",
                    "Email"
                ),
                "house_number": clean_required(
                    "house_number",
                    "House number"
                ),
                "province": clean_required(
                    "province",
                    "Province"
                ),
                "district": clean_required(
                    "district",
                    "District"
                ),
                "post_address": clean_required(
                    "post_address",
                    "Post address"
                ),
                "request_type": clean_required(
                    "request_type",
                    "TPN service requested"
                ),
                "additional_information": form_value(
                    "additional_information"
                ),
            }

            user = current_user()

            request_id, request_no = create_request(
                user["id"],
                "tpn",
                data
            )

            files = request.files.getlist(
                "supporting_documents"
            )

            for uploaded in files:
                if uploaded and uploaded.filename:
                    save_request_file(
                        request_id,
                        user["id"],
                        uploaded,
                        "tpn"
                    )

            flash(
                f"TPN request {request_no} "
                "was submitted successfully.",
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
            flash(
                f"TPN request failed: {exc}",
                "error"
            )

    province_options = "".join(
        f"<option>{e(p)}</option>"
        for p in PROVINCES
    )

    body = f"""
    <div class="card">

      <h2>📋 TPN Centre</h2>

      <p>
        KOJA TPN Centre handles TPIN
        registration, assistance, updates
        and related document requests.
      </p>

      <form
        method="post"
        enctype="multipart/form-data"
      >

        <div class="grid">

          <div class="field">
            <label>NRC Number *</label>
            <input name="nrc_number" required>
          </div>

          <div class="field">
            <label>Date of Birth *</label>
            <input
              type="date"
              name="date_of_birth"
              required
            >
          </div>

          <div class="field">
            <label>First Name *</label>
            <input name="first_name" required>
          </div>

          <div class="field">
            <label>Middle Names</label>
            <input name="middle_names">
          </div>

          <div class="field">
            <label>Last Name *</label>
            <input name="last_name" required>
          </div>

          <div class="field">
            <label>Gender *</label>

            <select name="gender" required>
              <option value="">
                Select gender
              </option>
              <option>Male</option>
              <option>Female</option>
              <option>Other</option>
            </select>
          </div>

          <div class="field">
            <label>Phone Number *</label>
            <input name="phone_number" required>
          </div>

          <div class="field">
            <label>Email *</label>
            <input
              type="email"
              name="email"
              required
            >
          </div>

          <div class="field">
            <label>House Number *</label>
            <input name="house_number" required>
          </div>

          <div class="field">
            <label>Province *</label>

            <select name="province" required>
              <option value="">
                Select Province
              </option>
              {province_options}
            </select>
          </div>

          <div class="field">
            <label>District *</label>
            <input name="district" required>
          </div>

          <div class="field">
            <label>Post Address *</label>
            <input name="post_address" required>
          </div>

        </div>

        <div class="field">

          <label>
            TPN Service Requested *
          </label>

          <select
            name="request_type"
            required
          >
            <option value="">
              Select request
            </option>
            <option>
              TPIN Registration
            </option>
            <option>
              TPIN Assistance
            </option>
            <option>
              TPIN Update
            </option>
            <option>
              TPIN Certificate / Document Request
            </option>
            <option>
              Other TPN Service
            </option>
          </select>

        </div>

        <div class="field">

          <label>
            Additional Information
          </label>

          <textarea
            name="additional_information"
          ></textarea>

        </div>

        <div class="field filebox">

          <label>
            Supporting Documents
          </label>

          <input
            type="file"
            name="supporting_documents"
            multiple
            accept=".pdf,.jpg,.jpeg,.png,.webp,.doc,.docx"
          >

          <div class="help">
            Maximum {MAX_FILE_MB} MB per file.
          </div>

        </div>

        <button class="btn green">
          Send TPN Request
        </button>

      </form>
    </div>
    """

    return page(
        "TPN Centre",
        body
    )


# ============================================================
# HIGHER EDUCATION MATERIALS
# ============================================================

@app.route(
    "/request/materials",
    methods=["GET", "POST"]
)
@login_required
def materials_request():
    if request.method == "POST":
        try:
            data = {
                "university": clean_required(
                    "university",
                    "University"
                ),
                "programme": clean_required(
                    "programme",
                    "Programme"
                ),
                "course": clean_required(
                    "course",
                    "Course / Subject"
                ),
                "academic_level": clean_required(
                    "academic_level",
                    "Academic level"
                ),
                "material_type": clean_required(
                    "material_type",
                    "Material type"
                ),
                "topic": clean_required(
                    "topic",
                    "Topic / Material needed"
                ),
                "description": form_value(
                    "description"
                ),
            }

            user = current_user()

            request_id, request_no = create_request(
                user["id"],
                "materials",
                data
            )

            files = request.files.getlist(
                "supporting_documents"
            )

            for uploaded in files:
                if uploaded and uploaded.filename:
                    save_request_file(
                        request_id,
                        user["id"],
                        uploaded,
                        "materials"
                    )

            flash(
                f"Materials request {request_no} "
                "was submitted successfully.",
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
            flash(
                f"Materials request failed: {exc}",
                "error"
            )

    body = """
    <div class="card">

      <h2>📖 Higher Education Materials</h2>

      <p>
        Request legitimate educational materials
        for your university or college studies.
      </p>

      <form
        method="post"
        enctype="multipart/form-data"
      >

        <div class="grid">

          <div class="field">
            <label>University / College *</label>
            <input name="university" required>
          </div>

          <div class="field">
            <label>Programme *</label>
            <input name="programme" required>
          </div>

          <div class="field">
            <label>Course / Subject *</label>
            <input name="course" required>
          </div>

          <div class="field">
            <label>Academic Level *</label>
            <input name="academic_level" required>
          </div>

          <div class="field">

            <label>Material Type *</label>

            <select
              name="material_type"
              required
            >
              <option value="">
                Select material
              </option>
              <option>
                Lecture Notes
              </option>
              <option>
                Study Guide
              </option>
              <option>
                Revision Material
              </option>
              <option>
                Past Paper
              </option>
              <option>
                Course Outline
              </option>
              <option>
                Other
              </option>
            </select>

          </div>

          <div class="field">
            <label>Topic / Material Needed *</label>
            <input name="topic" required>
          </div>

        </div>

        <div class="field">

          <label>
            Description
          </label>

          <textarea
            name="description"
            placeholder="Explain exactly what material you need."
          ></textarea>

        </div>

        <div class="field filebox">

          <label>
            Supporting Documents
          </label>

          <input
            type="file"
            name="supporting_documents"
            multiple
            accept=".pdf,.doc,.docx,.jpg,.jpeg,.png,.webp"
          >

        </div>

        <button class="btn green">
          Send Materials Request
        </button>

      </form>
    </div>
    """

    return page(
        "Higher Education Materials",
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
        "koja_requests",
        {
            "user_id": f"eq.{user['id']}",
            "order": "created_at.desc",
        }
    )

    table_rows = ""

    for row in rows:
        cls = status_class(
            row["status"]
        )

        table_rows += f"""
        <tr>

          <td>
            <a href="/request/{row['id']}">
              <strong>
                {e(row['request_no'])}
              </strong>
            </a>
          </td>

          <td>
            {e(row['service_name'])}
          </td>

          <td>
            {e(str(row['created_at'])[:10])}
          </td>

          <td>
            <span class="status {cls}">
              {e(row['status'])}
            </span>
          </td>

        </tr>
        """

    body = f"""
    <section class="card">

      <h2>My Requests</h2>

      <table class="data-table">

        <tr>
          <th>Request</th>
          <th>Service</th>
          <th>Date</th>
          <th>Status</th>
        </tr>

        {table_rows or
        '<tr><td colspan="4">No requests found.</td></tr>'}

      </table>

    </section>
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
    row = get_request(
        request_id
    )

    if not row:
        abort(404)

    user = current_user()

    if str(row["user_id"]) != str(user["id"]):
        abort(403)

    data = parse_request_data(row)

    files = get_request_files(
        request_id
    )

    items = ""

    for key, value in data.items():
        label = key.replace(
            "_",
            " "
        ).title()

        value_html = e(value).replace(
            "\n",
            "<br>"
        )

        items += f"""
        <div class="k">
          {e(label)}
        </div>

        <div>
          {value_html}
        </div>
        """

    file_items = ""

    for file_row in files:
        file_items += f"""
        <li>
          <a
            href="/file/{file_row['id']}"
            target="_blank"
          >
            {e(file_row['original_name'])}
          </a>
        </li>
        """

    output = ""

    if row.get("output_file"):
        output = f"""
        <section class="card">

          <h2>Completed Result</h2>

          <p>
            KOJA has uploaded a result
            for this request.
          </p>

          <a
            class="btn green"
            href="/download-result/{row['id']}"
          >
            Download Result
          </a>

        </section>
        """

    cls = status_class(
        row["status"]
    )

    body = f"""
    <section class="card">

      <h2>
        {e(row['request_no'])}
      </h2>

      <p>
        <strong>Service:</strong>
        {e(row['service_name'])}
      </p>

      <p>
        <strong>Status:</strong>

        <span class="status {cls}">
          {e(row['status'])}
        </span>
      </p>

      <p class="small">
        Submitted:
        {e(row['created_at'])}
      </p>

    </section>

    <section class="card">

      <h2>
        Request Details
      </h2>

      <div class="kv">
        {items}
      </div>

    </section>

    <section class="card">

      <h2>
        Documents
      </h2>

      <ul>
        {file_items or
        '<li>No documents attached.</li>'}
      </ul>

    </section>

    <section class="card">

      <h2>
        KOJA Response
      </h2>

      <p>
        {e(row.get("admin_response"))
        if row.get("admin_response")
        else "No admin response has been added yet."}
      </p>

    </section>

    {output}
    """

    return page(
        row["request_no"],
        body
    )


# ============================================================
# PRIVATE FILE
# ============================================================

@app.route(
    "/file/<file_id>"
)
@login_required
def private_file(file_id):
    rows = db_select(
        "koja_request_files",
        {
            "id": f"eq.{file_id}",
            "limit": "1",
        }
    )

    if not rows:
        abort(404)

    file_row = rows[0]

    user = current_user()

    request_row = get_request(
        file_row["request_id"]
    )

    if not request_row:
        abort(404)

    if str(request_row["user_id"]) != str(user["id"]):
        abort(403)

    response = storage_download(
        file_row["stored_path"]
    )

    content_type = (
        file_row.get("mime_type")
        or "application/octet-stream"
    )

    return send_file(
        __import__("io").BytesIO(
            response.content
        ),
        mimetype=content_type,
        as_attachment=False,
        download_name=file_row["original_name"],
    )


# ============================================================
# DOWNLOAD RESULT
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

    if str(row["user_id"]) != str(user["id"]):
        abort(403)

    if not row.get("output_file"):
        abort(404)

    response = storage_download(
        row["output_file"]
    )

    filename = (
        row.get("output_file_original")
        or "koja-result"
    )

    return send_file(
        __import__("io").BytesIO(
            response.content
        ),
        mimetype=(
            mimetypes.guess_type(
                filename
            )[0]
            or "application/octet-stream"
        ),
        as_attachment=True,
        download_name=filename,
    )


# ============================================================
# NOTIFICATIONS
# ============================================================

@app.route("/notifications")
@login_required
def notifications():
    user = current_user()

    rows = db_select(
        "koja_notifications",
        {
            "user_id": f"eq.{user['id']}",
            "order": "created_at.desc",
        }
    )

    try:
        db_update(
            "koja_notifications",
            {
                "user_id": f"eq.{user['id']}"
            },
            {
                "is_read": True
            }
        )
    except Exception:
        pass

    cards = ""

    for n in rows:
        cards += f"""
        <div class="card">

          <h3>
            {e(n['title'])}
          </h3>

          <p>
            {e(n['message'])}
          </p>

          <div class="small">
            {e(n['created_at'])}
          </div>

        </div>
        """

    body = (
        cards
        or
        """
        <div class="card">
          <h2>Notifications</h2>
          <p>No notifications yet.</p>
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
    <section class="card">

      <h2>Profile</h2>

      <div class="kv">

        <div class="k">
          Full Name
        </div>

        <div>
          {e(user['full_name'])}
        </div>

        <div class="k">
          Email
        </div>

        <div>
          {e(user['email'])}
        </div>

        <div class="k">
          Phone
        </div>

        <div>
          {e(user.get('phone'))}
        </div>

        <div class="k">
          Account Created
        </div>

        <div>
          {e(user['created_at'])}
        </div>

      </div>

    </section>
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
        email = form_value(
            "email"
        ).lower()

        password = request.form.get(
            "password",
            ""
        )

        try:
            email_ok = secrets.compare_digest(
                email,
                ADMIN_EMAIL
            )

            password_ok = secrets.compare_digest(
                password,
                ADMIN_PASSWORD
            )

            if email_ok and password_ok:
                session.clear()
                session["admin_logged_in"] = True

                return redirect(
                    url_for(
                        "admin_dashboard"
                    )
                )

            flash(
                "Invalid administrator credentials.",
                "error"
            )

        except Exception:
            flash(
                "Administrator login failed.",
                "error"
            )

    body = """
    <div class="card"
         style="max-width:600px;margin:auto">

      <h2>
        KOJA Administrator Login
      </h2>

      <p class="small">
        Administrator login is separate
        from client accounts.
      </p>

      <form method="post">

        <div class="field">
          <label>Admin Email *</label>

          <input
            type="email"
            name="email"
            required
          >
        </div>

        <div class="field">
          <label>Admin Password *</label>

          <input
            type="password"
            name="password"
            required
          >
        </div>

        <button class="btn green">
          Admin Login
        </button>

      </form>

    </div>
    """

    return page(
        "Admin Login",
        body
    )


# ============================================================
# ADMIN LOGOUT
# ============================================================

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
    status_filter = form_value(
        "status"
    )

    service_filter = form_value(
        "service"
    )

    params = {
        "order": "created_at.desc",
        "limit": "200",
    }

    if status_filter in STATUSES:
        params["status"] = (
            f"eq.{status_filter}"
        )

    if service_filter in SERVICE_NAMES:
        params["service_type"] = (
            f"eq.{service_filter}"
        )

    rows = db_select(
        "koja_requests",
        params
    )

    total = len(
        db_select(
            "koja_requests",
            {"select": "id"}
        )
    )

    counts = {}

    for status in STATUSES:
        counts[status] = len(
            db_select(
                "koja_requests",
                {
                    "status": f"eq.{status}",
                    "select": "id",
                }
            )
        )

    stat_cards = f"""
    <div class="grid3">

      <div class="service">
        <strong>Total</strong>
        <h2>{total}</h2>
      </div>

      <div class="service">
        <strong>Request Received</strong>
        <h2>{counts['Request Received']}</h2>
      </div>

      <div class="service">
        <strong>Processing</strong>
        <h2>{counts['Processing']}</h2>
      </div>

      <div class="service">
        <strong>Awaiting Client</strong>
        <h2>{counts['Awaiting Client']}</h2>
      </div>

      <div class="service">
        <strong>Completed</strong>
        <h2>{counts['Completed']}</h2>
      </div>

      <div class="service">
        <strong>Rejected</strong>
        <h2>{counts['Rejected']}</h2>
      </div>

    </div>
    """

    table_rows = ""

    for row in rows:
        user = get_user_by_id(
            row["user_id"]
        ) or {}

        cls = status_class(
            row["status"]
        )

        table_rows += f"""
        <tr>

          <td>
            <a
              href="/admin/request/{row['id']}"
            >
              <strong>
                {e(row['request_no'])}
              </strong>
            </a>
          </td>

          <td>
            {e(row['service_name'])}
          </td>

          <td>
            {e(user.get('full_name', ''))}
          </td>

          <td>
            {e(user.get('email', ''))}
          </td>

          <td>
            <span class="status {cls}">
              {e(row['status'])}
            </span>
          </td>

          <td>
            {e(str(row['created_at'])[:16])}
          </td>

        </tr>
        """

    service_options = ""

    for key, name, desc in SERVICE_LIST:
        service_options += (
            f'<option value="{e(key)}" '
            f'{"selected" if key == service_filter else ""}>'
            f'{e(name)}'
            f'</option>'
        )

    status_options = ""

    for status in STATUSES:
        status_options += (
            f'<option '
            f'{"selected" if status == status_filter else ""}>'
            f'{e(status)}'
            f'</option>'
        )

    body = f"""
    <section class="hero">

      <h1>KOJA Admin Dashboard</h1>

      <p>
        One place to manage all KOJA requests
        while keeping each service workflow separate.
      </p>

    </section>

    {stat_cards}

    <section class="card">

      <h2>Filter Requests</h2>

      <form method="get">

        <div class="grid">

          <div class="field">
            <label>Service</label>

            <select name="service">

              <option value="">
                All Services
              </option>

              {service_options}

            </select>
          </div>

          <div class="field">
            <label>Status</label>

            <select name="status">

              <option value="">
                All Statuses
              </option>

              {status_options}

            </select>
          </div>

        </div>

        <button class="btn green">
          Filter
        </button>

        <a
          class="btn light"
          href="/admin"
        >
          Clear
        </a>

      </form>

    </section>

    <section class="card">

      <h2>All KOJA Requests</h2>

      <table class="data-table">

        <tr>
          <th>Request</th>
          <th>Service</th>
          <th>Client</th>
          <th>Email</th>
          <th>Status</th>
          <th>Date</th>
        </tr>

        {table_rows or
        '<tr><td colspan="6">No requests found.</td></tr>'}

      </table>

    </section>
    """

    return page(
        "Admin Dashboard",
        body,
        admin=True
    )


# ============================================================
# ADMIN REQUEST DETAIL
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
        try:
            status = form_value(
                "status"
            )

            response_text = form_value(
                "admin_response"
            )

            if status not in STATUSES:
                raise ValueError(
                    "Invalid request status."
                )

            output = request.files.get(
                "result_file"
            )

            output_path = row.get(
                "output_file"
            )

            output_original = row.get(
                "output_file_original"
            )

            if output and output.filename:
                uploaded = storage_upload(
                    output,
                    "results",
                    str(request_id)
                )

                if uploaded:
                    output_path = uploaded[
                        "stored_path"
                    ]

                    output_original = uploaded[
                        "original_name"
                    ]

            db_update(
                "koja_requests",
                {
                    "id": f"eq.{request_id}"
                },
                {
                    "status": status,
                    "admin_response": response_text,
                    "output_file": output_path,
                    "output_file_original":
                        output_original,
                    "updated_at": now_iso(),
                }
            )

            add_notification(
                row["user_id"],
                f"Request Updated: {row['request_no']}",
                (
                    f"Your {row['service_name']} request "
                    f"is now '{status}'. "
                    + (
                        f"KOJA response: {response_text}"
                        if response_text
                        else ""
                    )
                )
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

        except ValueError as exc:
            flash(
                str(exc),
                "error"
            )

        except Exception as exc:
            flash(
                f"Request update failed: {exc}",
                "error"
            )

    data = parse_request_data(
        row
    )

    files = get_request_files(
        request_id
    )

    items = ""

    for key, value in data.items():
        items += f"""
        <div class="k">
          {e(key.replace('_', ' ').title())}
        </div>

        <div>
          {e(value).replace(chr(10), '<br>')}
        </div>
        """

    file_items = ""

    for f in files:
        file_items += f"""
        <li>
          <a
            href="/admin/file/{f['id']}"
            target="_blank"
          >
            {e(f['original_name'])}
          </a>
        </li>
        """

    selected = {}

    for status in STATUSES:
        selected[status] = (
            "selected"
            if row["status"] == status
            else ""
        )

    options = "".join(
        f'<option {selected[s]}>{e(s)}</option>'
        for s in STATUSES
    )

    body = f"""
    <section class="card">

      <h2>
        {e(row['request_no'])}
      </h2>

      <p>
        <strong>Service:</strong>
        {e(row['service_name'])}
      </p>

      <p>
        <strong>Client:</strong>
        {e(row.get('full_name'))}
      </p>

      <p>
        <strong>Email:</strong>
        {e(row.get('user_email'))}
      </p>

      <p>
        <strong>Phone:</strong>
        {e(row.get('user_phone'))}
      </p>

      <p>
        <strong>Status:</strong>

        <span class="status {status_class(row['status'])}">
          {e(row['status'])}
        </span>
      </p>

    </section>

    <section class="card">

      <h2>
        Submitted Information
      </h2>

      <div class="kv">
        {items}
      </div>

    </section>

    <section class="card">

      <h2>
        Client Documents
      </h2>

      <ul>
        {file_items or
        '<li>No documents.</li>'}
      </ul>

    </section>

    <section class="card">

      <h2>
        Process Request
      </h2>

      <form
        method="post"
        enctype="multipart/form-data"
      >

        <div class="field">

          <label>Status</label>

          <select name="status">
            {options}
          </select>

        </div>

        <div class="field">

          <label>KOJA Response</label>

          <textarea
            name="admin_response"
            placeholder="Enter progress, instructions or result information."
          >{e(row.get('admin_response'))}</textarea>

        </div>

        <div class="field filebox">

          <label>
            Upload Completed Result
          </label>

          <input
            type="file"
            name="result_file"
            accept=".pdf,.doc,.docx,.jpg,.jpeg,.png,.webp"
          >

          <div class="help">
            Upload the completed result
            that the client should receive.
            Maximum {MAX_FILE_MB} MB.
          </div>

        </div>

        <button class="btn green">
          Save Request Update
        </button>

      </form>

    </section>

    <a
      class="btn light"
      href="/admin"
    >
      ← Back to Admin Dashboard
    </a>
    """

    return page(
        "Admin Request",
        body,
        admin=True
    )


# ============================================================
# ADMIN FILE ACCESS
# ============================================================

@app.route(
    "/admin/file/<file_id>"
)
@admin_required
def admin_file(file_id):
    rows = db_select(
        "koja_request_files",
        {
            "id": f"eq.{file_id}",
            "limit": "1",
        }
    )

    if not rows:
        abort(404)

    file_row = rows[0]

    response = storage_download(
        file_row["stored_path"]
    )

    return send_file(
        __import__("io").BytesIO(
            response.content
        ),
        mimetype=(
            file_row.get("mime_type")
            or "application/octet-stream"
        ),
        as_attachment=False,
        download_name=file_row[
            "original_name"
        ],
    )


# ============================================================
# HEALTH CHECK
# ============================================================

@app.route("/health")
def health():
    result = {
        "status": "ok",
        "application": "KOJA AFRICA",
        "supabase_configured": bool(
            SUPABASE_URL
            and SUPABASE_SERVICE_KEY
        ),
        "storage_bucket": STORAGE_BUCKET,
        "time": now_iso(),
    }

    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        result["status"] = "configuration_error"

        return result, 503

    try:
        db_select(
            "koja_users",
            {
                "select": "id",
                "limit": "1",
            }
        )

        result["database"] = "connected"

        return result, 200

    except Exception as exc:
        result["status"] = "database_error"
        result["database"] = str(exc)

        return result, 503


# ============================================================
# ERROR HANDLERS
# ============================================================

@app.errorhandler(400)
def bad_request(error):
    body = """
    <div class="card">
      <h1>400</h1>
      <p>
        The request could not be understood.
      </p>
      <a class="btn green" href="/">
        Return Home
      </a>
    </div>
    """

    return page(
        "400",
        body
    ), 400


@app.errorhandler(403)
def forbidden(error):
    body = """
    <div class="card">
      <h1>403</h1>
      <p>
        You do not have permission to access
        this page.
      </p>
      <a class="btn green" href="/">
        Return Home
      </a>
    </div>
    """

    return page(
        "403",
        body
    ), 403


@app.errorhandler(404)
def not_found(error):
    body = """
    <div class="card">
      <h1>404</h1>
      <p>
        The page or request could not be found.
      </p>
      <a class="btn green" href="/">
        Return Home
      </a>
    </div>
    """

    return page(
        "404",
        body
    ), 404


@app.errorhandler(413)
def too_large(error):
    body = f"""
    <div class="card">
      <h1>File Too Large</h1>

      <p>
        The maximum upload size is
        {MAX_FILE_MB} MB.
      </p>

      <a class="btn green" href="/">
        Return Home
      </a>
    </div>
    """

    return page(
        "File Too Large",
        body
    ), 413


@app.errorhandler(500)
def server_error(error):
    body = """
    <div class="card">
      <h1>500</h1>

      <p>
        KOJA encountered an unexpected
        server error.
      </p>

      <a class="btn green" href="/">
        Return Home
      </a>
    </div>
    """

    return page(
        "Server Error",
        body
    ), 500


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

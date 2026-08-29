 import os
import json
import uuid
import sqlite3
import secrets
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path

from flask import (
    Flask, request, redirect, url_for, session,
    render_template_string, flash, send_from_directory, abort
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

# ============================================================
# KOJA AFRICA - SINGLE FILE FLASK APPLICATION
# Services are intentionally separated:
#   1. Farmer Registration -> 3-step farmer workflow
#   2. TPN Services        -> separate TPN workflow
#   3. University Request  -> separate university workflow
#   4. Other Services      -> simple service request
#
# Render:
#   Build command: pip install -r requirements.txt
#   Start command: gunicorn app:app
#
# ADMIN LOGIN IS SEPARATE FROM CLIENT LOGIN.
# Set these environment variables on Render:
#   ADMIN_EMAIL
#   ADMIN_PASSWORD
#   SECRET_KEY
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "koja_data"
UPLOAD_DIR = DATA_DIR / "uploads"
DB_PATH = DATA_DIR / "koja.db"

DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10 MB

ALLOWED_EXTENSIONS = {
    "pdf", "png", "jpg", "jpeg", "webp",
    "doc", "docx"
}

ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@koja-africa.com").strip().lower()
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "CHANGE-THIS-ADMIN-PASSWORD")

PROVINCES = [
    "Central", "Copperbelt", "Eastern", "Luapula", "Lusaka",
    "Muchinga", "Northern", "North-Western", "Southern", "Western"
]

GENDERS = ["Male", "Female", "Other"]

FARMER_PAYMENT_METHODS = [
    "Bank Account",
    "Mobile Money"
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
    "Zanaco"
]

MOBILE_PROVIDERS = ["Airtel Money", "MTN MoMo", "Zamtel Kwacha"]

SERVICE_LIST = [
    ("farmer", "Farmer Registration", "Complete the farmer registration workflow."),
    ("tpin", "TPIN Services", "Submit your TPIN-related request and personal information."),
    ("university", "University Request", "Submit a university-related request to KOJA."),
    ("other", "Other Services", "Send another service request to KOJA."),
]


# ============================================================
# DATABASE
# ============================================================

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = db()

    conn.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        full_name TEXT NOT NULL,
        email TEXT NOT NULL UNIQUE,
        phone TEXT,
        password_hash TEXT NOT NULL,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        request_no TEXT NOT NULL UNIQUE,
        user_id INTEGER NOT NULL,
        service_type TEXT NOT NULL,
        service_name TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'Request Received',
        data_json TEXT NOT NULL DEFAULT '{}',
        admin_response TEXT,
        output_file TEXT,
        output_file_original TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS request_files (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        request_id INTEGER NOT NULL,
        original_name TEXT NOT NULL,
        stored_name TEXT NOT NULL,
        file_type TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY(request_id) REFERENCES requests(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        message TEXT NOT NULL,
        is_read INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    """)

    conn.commit()
    conn.close()


init_db()


# ============================================================
# HELPERS
# ============================================================

def now_iso():
    return datetime.now(timezone.utc).isoformat()


def service_name(service_type):
    return dict((x[0], x[1]) for x in SERVICE_LIST).get(
        service_type, "KOJA Service"
    )


def new_request_no():
    stamp = datetime.now().strftime("%Y%m%d")
    return f"KOJA-{stamp}-{secrets.token_hex(4).upper()}"


def allowed_file(filename):
    return (
        "." in filename and
        filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
    )


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            flash("Please create an account or log in first.", "error")
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


def current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    conn = db()
    row = conn.execute(
        "SELECT * FROM users WHERE id = ?", (uid,)
    ).fetchone()
    conn.close()
    return row


def add_notification(user_id, title, message):
    conn = db()
    conn.execute(
        """
        INSERT INTO notifications
        (user_id, title, message, is_read, created_at)
        VALUES (?, ?, ?, 0, ?)
        """,
        (user_id, title, message, now_iso())
    )
    conn.commit()
    conn.close()


def save_uploaded_file(file_storage, request_id):
    if not file_storage or not file_storage.filename:
        return None

    original = secure_filename(file_storage.filename)
    if not original or not allowed_file(original):
        raise ValueError(
            "Unsupported file type. Use PDF, Word, JPG, PNG or WEBP."
        )

    ext = original.rsplit(".", 1)[1].lower()
    stored = f"{uuid.uuid4().hex}.{ext}"
    destination = UPLOAD_DIR / stored
    file_storage.save(destination)

    conn = db()
    conn.execute(
        """
        INSERT INTO request_files
        (request_id, original_name, stored_name, file_type, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (request_id, original, stored, ext, now_iso())
    )
    conn.commit()
    conn.close()

    return stored


def create_request(user_id, service_type, data):
    request_no = new_request_no()
    created = now_iso()
    conn = db()

    conn.execute(
        """
        INSERT INTO requests
        (request_no, user_id, service_type, service_name, status,
         data_json, created_at, updated_at)
        VALUES (?, ?, ?, ?, 'Request Received', ?, ?, ?)
        """,
        (
            request_no,
            user_id,
            service_type,
            service_name(service_type),
            json.dumps(data, ensure_ascii=False),
            created,
            created
        )
    )

    conn.commit()
    row = conn.execute(
        "SELECT id FROM requests WHERE request_no = ?",
        (request_no,)
    ).fetchone()
    conn.close()

    add_notification(
        user_id,
        "Request Received",
        f"Your {service_name(service_type)} request {request_no} has been received by KOJA."
    )

    return row["id"], request_no


def get_request(request_id):
    conn = db()
    row = conn.execute(
        """
        SELECT r.*, u.full_name, u.email AS user_email, u.phone AS user_phone
        FROM requests r
        JOIN users u ON u.id = r.user_id
        WHERE r.id = ?
        """,
        (request_id,)
    ).fetchone()
    conn.close()
    return row


def get_request_files(request_id):
    conn = db()
    rows = conn.execute(
        """
        SELECT * FROM request_files
        WHERE request_id = ?
        ORDER BY id DESC
        """,
        (request_id,)
    ).fetchall()
    conn.close()
    return rows


def clean_required(name, label=None):
    value = request.form.get(name, "").strip()
    if not value:
        raise ValueError(f"{label or name.replace('_', ' ').title()} is required.")
    return value


def parse_json(row):
    try:
        return json.loads(row["data_json"] or "{}")
    except Exception:
        return {}


# ============================================================
# HTML / DESIGN
# ============================================================

CSS = """
<style>
:root{
    --blue:#214f91;
    --green:#19733f;
    --green2:#238b52;
    --ink:#172235;
    --muted:#667085;
    --bg:#f4f7fb;
    --card:#ffffff;
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
a{text-decoration:none;color:inherit}
.nav{
    background:#fff;
    border-bottom:1px solid var(--line);
    position:sticky;
    top:0;
    z-index:10;
}
.nav-inner{
    max-width:1100px;
    margin:auto;
    padding:18px 22px;
    display:flex;
    align-items:center;
    justify-content:space-between;
    gap:20px;
}
.logo{
    color:var(--blue);
    font-size:29px;
    font-weight:800;
    letter-spacing:-1px;
}
.navlinks{
    display:flex;
    flex-wrap:wrap;
    gap:8px;
    justify-content:flex-end;
}
.navlinks a{
    padding:10px 13px;
    border-radius:9px;
    color:#26364c;
    font-size:15px;
}
.navlinks a:hover{background:#eef4fb}
.container{
    max-width:1100px;
    margin:0 auto;
    padding:34px 20px 60px;
}
.hero{
    background:linear-gradient(135deg,#eef5ff,#fff);
    border:1px solid #dfe9f7;
    border-radius:24px;
    padding:42px 32px;
    margin-bottom:25px;
}
.hero h1{font-size:42px;margin:0 0 12px;color:var(--blue)}
.hero p{font-size:19px;color:var(--muted);line-height:1.6}
.card{
    background:var(--card);
    border:1px solid var(--line);
    border-radius:22px;
    padding:28px;
    margin-bottom:22px;
    box-shadow:0 5px 18px rgba(25,45,70,.05);
}
.card h2{margin-top:0}
.grid{
    display:grid;
    grid-template-columns:repeat(2,minmax(0,1fr));
    gap:18px;
}
.grid3{
    display:grid;
    grid-template-columns:repeat(3,minmax(0,1fr));
    gap:18px;
}
label{
    display:block;
    font-weight:600;
    margin:0 0 8px;
}
input,select,textarea{
    width:100%;
    padding:14px 15px;
    border:1px solid #cfd7e2;
    border-radius:11px;
    font-size:16px;
    background:#fff;
    color:var(--ink);
}
textarea{min-height:130px;resize:vertical}
.field{margin-bottom:18px}
.help{font-size:13px;color:var(--muted);margin-top:6px}
.btn{
    display:inline-block;
    border:0;
    cursor:pointer;
    padding:13px 18px;
    border-radius:11px;
    font-size:16px;
    font-weight:700;
    background:var(--blue);
    color:white;
}
.btn.green{background:var(--green)}
.btn.light{background:#eef4fb;color:var(--blue)}
.btn.danger{background:var(--danger)}
.actions{
    display:flex;
    gap:12px;
    flex-wrap:wrap;
    margin-top:20px;
}
.service{
    border:1px solid var(--line);
    border-radius:18px;
    padding:23px;
    background:#fff;
    transition:.15s;
}
.service:hover{transform:translateY(-2px);box-shadow:0 8px 22px rgba(20,40,70,.08)}
.service h3{margin:0 0 8px}
.service p{color:var(--muted);line-height:1.5;min-height:46px}
.stepbar{
    display:flex;
    gap:10px;
    justify-content:center;
    margin:10px 0 28px;
}
.step{
    width:46px;height:46px;border-radius:50%;
    display:flex;align-items:center;justify-content:center;
    background:#e4e8ee;color:#566274;font-weight:800;
}
.step.done,.step.active{background:var(--green);color:white}
.step.active{box-shadow:0 0 0 7px #d7f0e3}
.alert{
    border-radius:12px;padding:13px 16px;margin-bottom:18px;
}
.alert.success{background:#e6f6ed;color:#146437}
.alert.error{background:#fdecec;color:#a22626}
.alert.info{background:#eaf2fc;color:#24508e}
.status{
    display:inline-block;
    padding:8px 12px;
    border-radius:999px;
    background:#e9f2fc;
    color:#24508e;
    font-weight:700;
}
.status.completed{background:#e4f6eb;color:#176d3d}
.status.processing{background:#fff4d8;color:#7b5600}
.status.rejected{background:#fde8e8;color:#9e2525}
.status.received{background:#e9f2fc;color:#24508e}
.data-table{
    width:100%;
    border-collapse:collapse;
}
.data-table th,.data-table td{
    padding:12px 10px;
    border-bottom:1px solid var(--line);
    text-align:left;
    vertical-align:top;
}
.data-table th{font-size:13px;color:var(--muted)}
.kv{
    display:grid;
    grid-template-columns:210px 1fr;
    gap:0;
}
.kv div{
    padding:11px 0;
    border-bottom:1px solid #edf0f4;
}
.kv .k{font-weight:700;color:#405067}
.footer{
    text-align:center;
    padding:35px 20px;
    color:#7b8798;
}
.filebox{
    background:#f7f9fc;
    border:1px dashed #cbd5e1;
    padding:16px;
    border-radius:12px;
}
.admin-top{
    background:#13263e;
    color:white;
    padding:16px 22px;
}
.admin-top-inner{
    max-width:1100px;margin:auto;
    display:flex;justify-content:space-between;align-items:center;
}
.small{font-size:13px;color:var(--muted)}
@media(max-width:760px){
    .nav-inner{align-items:flex-start;flex-direction:column}
    .navlinks{justify-content:flex-start}
    .hero h1{font-size:31px}
    .grid,.grid3{grid-template-columns:1fr}
    .card{padding:21px}
    .container{padding:23px 14px 45px}
    .kv{grid-template-columns:1fr}
}
</style>
"""


def page(title, body, admin=False):
    user = current_user()
    if admin:
        nav = f"""
        <div class="admin-top">
          <div class="admin-top-inner">
            <strong>KOJA AFRICA — ADMIN</strong>
            <a href="{url_for('admin_logout')}" style="color:white">Admin Logout</a>
          </div>
        </div>
        """
    else:
        links = []
        if user:
            links = [
                ("Home", url_for("dashboard")),
                ("KOJA Services", url_for("services")),
                ("My Requests", url_for("my_requests")),
                ("Notifications", url_for("notifications")),
                ("Profile", url_for("profile")),
                ("Logout", url_for("logout")),
            ]
        else:
            links = [
                ("Home", url_for("home")),
                ("Client Login", url_for("login")),
                ("Create Account", url_for("register")),
            ]
        nav = f"""
        <nav class="nav">
          <div class="nav-inner">
            <a class="logo" href="{url_for('dashboard' if user else 'home')}">KOJA AFRICA</a>
            <div class="navlinks">
              {''.join(f'<a href="{u}">{n}</a>' for n,u in links)}
            </div>
          </div>
        </nav>
        """

    flashes = ""
    for category, message in list(get_flashed_messages(with_categories=True)):
        flashes += f'<div class="alert {category}">{message}</div>'

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
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
</html>"""


# ============================================================
# HOME / AUTH
# ============================================================

from flask import get_flashed_messages


@app.route("/")
def home():
    body = """
    <section class="hero">
      <h1>KOJA AFRICA</h1>
      <p>Services, requests and support in one place.</p>
      <div class="actions">
        <a class="btn" href="/register">Create Account</a>
        <a class="btn light" href="/login">Client Login</a>
      </div>
    </section>

    <section class="card">
      <h2>KOJA Services</h2>
      <p>Clients create an account, log in, select a service, enter the required information and submit a request to KOJA.</p>
      <div class="grid3">
        <div class="service"><h3>Farmer Services</h3><p>Separate three-step farmer registration workflow.</p></div>
        <div class="service"><h3>TPN Services</h3><p>Separate TPIN/TPN personal-information request workflow.</p></div>
        <div class="service"><h3>University Request</h3><p>University requests remain separate from farmer registration.</p></div>
      </div>
    </section>
    """
    return page("Home", body)


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")

        if not full_name or not email or not password:
            flash("Name, email and password are required.", "error")
        elif password != confirm:
            flash("Passwords do not match.", "error")
        elif len(password) < 6:
            flash("Password must be at least 6 characters.", "error")
        else:
            try:
                conn = db()
                conn.execute(
                    """
                    INSERT INTO users
                    (full_name,email,phone,password_hash,created_at)
                    VALUES (?,?,?,?,?)
                    """,
                    (
                        full_name, email, phone,
                        generate_password_hash(password),
                        now_iso()
                    )
                )
                conn.commit()
                conn.close()
                flash("Account created. You can now log in.", "success")
                return redirect(url_for("login"))
            except sqlite3.IntegrityError:
                flash("That email is already registered.", "error")

    body = """
    <div class="card">
      <h2>Create KOJA Account</h2>
      <p class="small">Create your client account before accessing KOJA Services.</p>
      <form method="post">
        <div class="grid">
          <div class="field">
            <label>Full Name *</label>
            <input name="full_name" required>
          </div>
          <div class="field">
            <label>Phone</label>
            <input name="phone">
          </div>
          <div class="field">
            <label>Email *</label>
            <input type="email" name="email" required>
          </div>
          <div class="field">
            <label>Password *</label>
            <input type="password" name="password" required>
          </div>
          <div class="field">
            <label>Confirm Password *</label>
            <input type="password" name="confirm_password" required>
          </div>
        </div>
        <button class="btn green">Create Account</button>
      </form>
    </div>
    """
    return page("Create Account", body)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        conn = db()
        user = conn.execute(
            "SELECT * FROM users WHERE email = ?", (email,)
        ).fetchone()
        conn.close()

        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            return redirect(url_for("dashboard"))

        flash("Invalid email or password.", "error")

    body = """
    <div class="card">
      <h2>Client Login</h2>
      <form method="post">
        <div class="field">
          <label>Email *</label>
          <input type="email" name="email" required>
        </div>
        <div class="field">
          <label>Password *</label>
          <input type="password" name="password" required>
        </div>
        <button class="btn">Login</button>
      </form>
      <div class="actions">
        <a href="/register" class="btn light">Create Account</a>
      </div>
    </div>
    """
    return page("Client Login", body)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


# ============================================================
# CLIENT DASHBOARD / SERVICES
# ============================================================

@app.route("/dashboard")
@login_required
def dashboard():
    user = current_user()
    conn = db()
    counts = {}
    for status in [
        "Request Received", "Processing",
        "Completed", "Rejected"
    ]:
        counts[status] = conn.execute(
            "SELECT COUNT(*) c FROM requests WHERE user_id=? AND status=?",
            (user["id"], status)
        ).fetchone()["c"]
    recent = conn.execute(
        """
        SELECT * FROM requests
        WHERE user_id=?
        ORDER BY id DESC LIMIT 5
        """,
        (user["id"],)
    ).fetchall()
    conn.close()

    cards = "".join(
        f"""
        <div class="service">
          <strong>{k}</strong>
          <div style="font-size:30px;margin-top:8px">{v}</div>
        </div>
        """
        for k,v in counts.items()
    )

    rows = ""
    for r in recent:
        cls = (
            "completed" if r["status"] == "Completed"
            else "processing" if r["status"] == "Processing"
            else "rejected" if r["status"] == "Rejected"
            else "received"
        )
        rows += f"""
        <tr>
          <td><a href="/request/{r['id']}"><strong>{r['request_no']}</strong></a></td>
          <td>{r['service_name']}</td>
          <td><span class="status {cls}">{r['status']}</span></td>
        </tr>
        """

    body = f"""
    <section class="hero">
      <h1>Welcome, {user['full_name']}</h1>
      <p>Select a KOJA service and submit your request. Each service uses its own required information.</p>
      <a class="btn green" href="/services">KOJA Services</a>
    </section>

    <div class="grid3">{cards}</div>

    <section class="card">
      <h2>Recent Requests</h2>
      <table class="data-table">
        <tr><th>Request</th><th>Service</th><th>Status</th></tr>
        {rows or '<tr><td colspan="3">No requests yet.</td></tr>'}
      </table>
    </section>
    """
    return page("Dashboard", body)


@app.route("/services")
@login_required
def services():
    items = ""
    for key, name, desc in SERVICE_LIST:
        items += f"""
        <div class="service">
          <h3>{name}</h3>
          <p>{desc}</p>
          <a class="btn {'green' if key in ('farmer','tpin') else ''}"
             href="/request/{key}">Open Service</a>
        </div>
        """

    body = f"""
    <section class="card">
      <h2>KOJA Services</h2>
      <p>Choose the service you need. The forms are intentionally separate.</p>
      <div class="grid2"></div>
      <div class="grid">{items}</div>
    </section>
    """
    return page("KOJA Services", body)


# ============================================================
# FARMER SERVICE - STEP 1
# ============================================================

@app.route("/request/farmer", methods=["GET", "POST"])
@login_required
def farmer_step1():
    if request.method == "POST":
        try:
            data = {
                "nrc": clean_required("nrc", "NRC"),
                "date_of_birth": clean_required("date_of_birth", "Date of birth"),
                "first_name": clean_required("first_name", "First name"),
                "middle_names": request.form.get("middle_names", "").strip(),
                "last_name": clean_required("last_name", "Last name"),
                "gender": clean_required("gender", "Gender"),
                "phone": clean_required("phone", "Phone"),
            }

            dob = data["date_of_birth"]
            if len(dob) != 10:
                raise ValueError("Enter date of birth in YYYY-MM-DD format.")

            session["farmer_data"] = data
            session["farmer_step"] = 2
            return redirect(url_for("farmer_step2"))

        except ValueError as e:
            flash(str(e), "error")

    body = """
    <div class="card">
      <h2 style="text-align:center;color:#19733f">Farmer Registration</h2>
      <p style="text-align:center;color:#667085;font-size:18px">
        Register to submit your farmer request through KOJA
      </p>

      <div class="stepbar">
        <div class="step active">1</div>
        <div class="step">2</div>
        <div class="step">3</div>
      </div>

      <h2>Step 1: Personal Details</h2>
      <p>Enter your personal information.</p>
      <hr>

      <form method="post">
        <div class="grid">
          <div class="field">
            <label>NRC *</label>
            <input name="nrc" placeholder="e.g. 123456/10/1" required>
          </div>

          <div class="field">
            <label>Date of Birth *</label>
            <input type="date" name="date_of_birth" required>
          </div>

          <div class="field">
            <label>First Name *</label>
            <input name="first_name" required>
          </div>

          <div class="field">
            <label>Middle Names</label>
            <input name="middle_names" placeholder="Optional">
          </div>

          <div class="field">
            <label>Last Name *</label>
            <input name="last_name" required>
          </div>

          <div class="field">
            <label>Gender *</label>
            <select name="gender" required>
              <option value="">Select gender</option>
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

        <div class="field filebox">
          <label>NRC Card</label>
          <input type="file" name="nrc_card" disabled>
          <div class="help">
            The file is collected on Step 1. Upload is enabled after this
            page is submitted so the step remains simple on mobile.
          </div>
        </div>

        <div class="actions">
          <button class="btn green">Continue to Location →</button>
        </div>
      </form>
    </div>
    """
    return page("Farmer Registration - Step 1", body)


# ============================================================
# FARMER SERVICE - STEP 2
# ============================================================

@app.route("/request/farmer/location", methods=["GET", "POST"])
@login_required
def farmer_step2():
    if "farmer_data" not in session:
        return redirect(url_for("farmer_step1"))

    if request.method == "POST":
        try:
            data = dict(session["farmer_data"])
            data.update({
                "province": clean_required("province", "Province"),
                "district": clean_required("district", "District"),
                "constituency": request.form.get("constituency", "").strip(),
                "chiefdom": request.form.get("chiefdom", "").strip(),
                "farming_area": clean_required("farming_area", "Farming location/area"),
            })

            session["farmer_data"] = data
            session["farmer_step"] = 3
            return redirect(url_for("farmer_step3"))

        except ValueError as e:
            flash(str(e), "error")

    body = """
    <div class="card">
      <h2 style="text-align:center;color:#19733f">Farmer Registration</h2>
      <div class="stepbar">
        <div class="step done">✓</div>
        <div class="step active">2</div>
        <div class="step">3</div>
      </div>

      <h2>Step 2: Your Location</h2>
      <p>Select or enter your farming location.</p>
      <hr>

      <form method="post">
        <div class="field">
          <label>Province *</label>
          <select name="province" required>
            <option value="">Select Province</option>
            """ + "".join(f"<option>{p}</option>" for p in PROVINCES) + """
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
            <input name="farming_area" required>
          </div>
        </div>

        <div class="actions">
          <a class="btn light" href="/request/farmer">← Back</a>
          <button class="btn green">Continue to Payment →</button>
        </div>
      </form>
    </div>
    """
    return page("Farmer Registration - Step 2", body)


# ============================================================
# FARMER SERVICE - STEP 3
# ============================================================

@app.route("/request/farmer/payment", methods=["GET", "POST"])
@login_required
def farmer_step3():
    if "farmer_data" not in session:
        return redirect(url_for("farmer_step1"))

    if request.method == "POST":
        try:
            data = dict(session["farmer_data"])
            method = clean_required("payment_method", "Payment method")
            provider = clean_required("provider", "Provider")
            account_no = clean_required("account_no", "Account number")
            account_name = clean_required("account_name", "Account name")

            data.update({
                "payment_method": method,
                "provider": provider,
                "branch": request.form.get("branch", "").strip(),
                "account_no": account_no,
                "account_name": account_name,
            })

            user = current_user()
            request_id, request_no = create_request(
                user["id"], "farmer", data
            )

            # Optional NRC upload on final submission.
            file = request.files.get("nrc_card")
            if file and file.filename:
                try:
                    save_uploaded_file(file, request_id)
                except ValueError as e:
                    flash(str(e), "error")
                    return redirect(url_for("farmer_step3"))

            session.pop("farmer_data", None)
            session.pop("farmer_step", None)

            flash(f"Farmer request {request_no} submitted successfully.", "success")
            return redirect(url_for("request_detail", request_id=request_id))

        except ValueError as e:
            flash(str(e), "error")

    body = """
    <div class="card">
      <h2 style="text-align:center;color:#19733f">Farmer Registration</h2>
      <div class="stepbar">
        <div class="step done">✓</div>
        <div class="step done">✓</div>
        <div class="step active">3</div>
      </div>

      <h2>Step 3: Payment & Submit</h2>
      <p>Enter payment details and submit the farmer request.</p>
      <hr>

      <form method="post" enctype="multipart/form-data">
        <div class="field">
          <label>Method *</label>
          <select name="payment_method" id="payment_method" required onchange="updateProviders()">
            <option value="">Select method</option>
            <option>Bank Account</option>
            <option>Mobile Money</option>
          </select>
        </div>

        <div class="field">
          <label>Provider *</label>
          <select name="provider" id="provider" required>
            <option value="">-- select provider --</option>
          </select>
        </div>

        <div class="field">
          <label>Branch</label>
          <input name="branch" placeholder="Bank branch, if applicable">
        </div>

        <div class="grid">
          <div class="field">
            <label>Account No. *</label>
            <input name="account_no" required>
          </div>

          <div class="field">
            <label>Account Name *</label>
            <input name="account_name" required>
            <div class="help">Auto-enter your full account holder name.</div>
          </div>
        </div>

        <div class="field filebox">
          <label>NRC Card / Supporting Document</label>
          <input type="file" name="nrc_card" accept=".pdf,.jpg,.jpeg,.png,.webp,.doc,.docx">
          <div class="help">PDF, Word or image. Maximum 10 MB.</div>
        </div>

        <div class="actions">
          <a class="btn light" href="/request/farmer/location">← Back</a>
          <button class="btn green">Submit Farmer Request</button>
        </div>
      </form>
    </div>

    <script>
    const banks = %s;
    const mobiles = %s;

    function updateProviders(){
      const method = document.getElementById("payment_method").value;
      const provider = document.getElementById("provider");
      provider.innerHTML = '<option value="">-- select provider --</option>';

      let list = method === "Bank Account" ? banks :
                 method === "Mobile Money" ? mobiles : [];

      list.forEach(function(x){
        const o = document.createElement("option");
        o.textContent = x;
        o.value = x;
        provider.appendChild(o);
      });
    }
    </script>
    """ % (json.dumps(BANKS), json.dumps(MOBILE_PROVIDERS))

    return page("Farmer Registration - Step 3", body)


# ============================================================
# TPIN SERVICE - SEPARATE WORKFLOW
# ============================================================

@app.route("/request/tpin", methods=["GET", "POST"])
@login_required
def tpin_request():
    if request.method == "POST":
        try:
            data = {
                "nrc_number": clean_required("nrc_number", "NRC number"),
                "date_of_birth": clean_required("date_of_birth", "Date of birth"),
                "first_name": clean_required("first_name", "First name"),
                "middle_names": request.form.get("middle_names", "").strip(),
                "last_name": clean_required("last_name", "Last name"),
                "gender": clean_required("gender", "Gender"),
                "phone_number": clean_required("phone_number", "Phone number"),
                "email": clean_required("email", "Email"),
                "house_number": clean_required("house_number", "House number"),
                "province": clean_required("province", "Province"),
                "district": clean_required("district", "District"),
                "post_address": clean_required("post_address", "Post address"),
                "request_type": clean_required("request_type", "TPIN service requested"),
                "additional_information": request.form.get(
                    "additional_information", ""
                ).strip()
            }

            user = current_user()
            request_id, request_no = create_request(
                user["id"], "tpin", data
            )

            files = request.files.getlist("supporting_documents")
            for file in files:
                if file and file.filename:
                    save_uploaded_file(file, request_id)

            flash(f"TPIN request {request_no} submitted successfully.", "success")
            return redirect(url_for("request_detail", request_id=request_id))

        except ValueError as e:
            flash(str(e), "error")

    body = """
    <div class="card">
      <h2 style="text-align:center;color:#214f91">TPIN Services</h2>
      <p style="text-align:center;color:#667085;font-size:18px">
        Enter the personal information required for your TPIN request.
      </p>

      <div class="stepbar">
        <div class="step active">1</div>
        <div class="step">2</div>
        <div class="step">3</div>
      </div>

      <h2>TPIN Request: Personal Information</h2>
      <p>TPIN is a separate KOJA service and does not use the farmer registration form.</p>
      <hr>

      <form method="post" enctype="multipart/form-data">
        <div class="grid">
          <div class="field">
            <label>NRC Number *</label>
            <input name="nrc_number" required>
          </div>

          <div class="field">
            <label>Date of Birth *</label>
            <input type="date" name="date_of_birth" required>
          </div>

          <div class="field">
            <label>First Name *</label>
            <input name="first_name" required>
          </div>

          <div class="field">
            <label>Middle Names</label>
            <input name="middle_names" placeholder="Optional">
          </div>

          <div class="field">
            <label>Last Name *</label>
            <input name="last_name" required>
          </div>

          <div class="field">
            <label>Gender *</label>
            <select name="gender" required>
              <option value="">Select gender</option>
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
            <input type="email" name="email" required>
          </div>

          <div class="field">
            <label>House Number *</label>
            <input name="house_number" required>
          </div>

          <div class="field">
            <label>Province *</label>
            <select name="province" required>
              <option value="">Select Province</option>
              """ + "".join(f"<option>{p}</option>" for p in PROVINCES) + """
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

          <div class="field">
            <label>TPIN Service Requested *</label>
            <select name="request_type" required>
              <option value="">Select request</option>
              <option>TPIN Registration</option>
              <option>TPIN Certificate / Document Request</option>
              <option>TPIN Update</option>
              <option>TPIN Assistance</option>
              <option>Other TPIN Service</option>
            </select>
          </div>
        </div>

        <div class="field">
          <label>Additional Information</label>
          <textarea name="additional_information"
            placeholder="Enter any additional information KOJA should receive."></textarea>
        </div>

        <div class="field filebox">
          <label>Supporting Documents</label>
          <input type="file" name="supporting_documents" multiple
                 accept=".pdf,.jpg,.jpeg,.png,.webp,.doc,.docx">
          <div class="help">Maximum 10 MB per request.</div>
        </div>

        <div class="actions">
          <a class="btn light" href="/services">← Back to Services</a>
          <button class="btn">Submit TPIN Request</button>
        </div>
      </form>
    </div>
    """
    return page("TPIN Services", body)


# ============================================================
# UNIVERSITY SERVICE - SEPARATE WORKFLOW
# ============================================================

@app.route("/request/university", methods=["GET", "POST"])
@login_required
def university_request():
    if request.method == "POST":
        try:
            data = {
                "university": clean_required("university", "University"),
                "request_type": clean_required("request_type", "Request type"),
                "student_number": request.form.get("student_number", "").strip(),
                "programme": request.form.get("programme", "").strip(),
                "academic_level": request.form.get("academic_level", "").strip(),
                "description": clean_required("description", "Description"),
            }

            user = current_user()
            request_id, request_no = create_request(
                user["id"], "university", data
            )

            files = request.files.getlist("documents")
            for file in files:
                if file and file.filename:
                    save_uploaded_file(file, request_id)

            flash(
                f"University request {request_no} submitted successfully.",
                "success"
            )
            return redirect(url_for("request_detail", request_id=request_id))

        except ValueError as e:
            flash(str(e), "error")

    body = """
    <div class="card">
      <h2>University Request</h2>
      <p>This service is separate from Farmer Registration and TPIN Services.</p>
      <form method="post" enctype="multipart/form-data">
        <div class="grid">
          <div class="field">
            <label>University *</label>
            <input name="university" required>
          </div>
          <div class="field">
            <label>Request Type *</label>
            <select name="request_type" required>
              <option value="">Select request</option>
              <option>Application Assistance</option>
              <option>Academic Request</option>
              <option>Student Records Request</option>
              <option>Verification Request</option>
              <option>Other University Request</option>
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
          <textarea name="description" required></textarea>
        </div>

        <div class="field filebox">
          <label>Supporting Documents</label>
          <input type="file" name="documents" multiple
                 accept=".pdf,.jpg,.jpeg,.png,.webp,.doc,.docx">
          <div class="help">Maximum 10 MB per request.</div>
        </div>

        <button class="btn">Submit University Request</button>
      </form>
    </div>
    """
    return page("University Request", body)


# ============================================================
# OTHER SERVICES
# ============================================================

@app.route("/request/other", methods=["GET", "POST"])
@login_required
def other_request():
    if request.method == "POST":
        try:
            data = {
                "service_title": clean_required("service_title", "Service title"),
                "description": clean_required("description", "Description"),
                "additional_information": request.form.get(
                    "additional_information", ""
                ).strip()
            }

            user = current_user()
            request_id, request_no = create_request(
                user["id"], "other", data
            )

            files = request.files.getlist("documents")
            for file in files:
                if file and file.filename:
                    save_uploaded_file(file, request_id)

            flash(
                f"Service request {request_no} submitted successfully.",
                "success"
            )
            return redirect(url_for("request_detail", request_id=request_id))

        except ValueError as e:
            flash(str(e), "error")

    body = """
    <div class="card">
      <h2>Other KOJA Service</h2>
      <form method="post" enctype="multipart/form-data">
        <div class="field">
          <label>Service / Request Title *</label>
          <input name="service_title" required>
        </div>
        <div class="field">
          <label>Description *</label>
          <textarea name="description" required></textarea>
        </div>
        <div class="field">
          <label>Additional Information</label>
          <textarea name="additional_information"></textarea>
        </div>
        <div class="field filebox">
          <label>Documents</label>
          <input type="file" name="documents" multiple
                 accept=".pdf,.jpg,.jpeg,.png,.webp,.doc,.docx">
          <div class="help">Maximum 10 MB per request.</div>
        </div>
        <button class="btn">Submit Request</button>
      </form>
    </div>
    """
    return page("Other Services", body)


# ============================================================
# REQUESTS / NOTIFICATIONS / PROFILE
# ============================================================

@app.route("/my-requests")
@login_required
def my_requests():
    user = current_user()
    conn = db()
    rows = conn.execute(
        """
        SELECT * FROM requests
        WHERE user_id=?
        ORDER BY id DESC
        """,
        (user["id"],)
    ).fetchall()
    conn.close()

    body_rows = ""
    for r in rows:
        cls = (
            "completed" if r["status"] == "Completed"
            else "processing" if r["status"] == "Processing"
            else "rejected" if r["status"] == "Rejected"
            else "received"
        )
        body_rows += f"""
        <tr>
          <td><a href="/request/{r['id']}"><strong>{r['request_no']}</strong></a></td>
          <td>{r['service_name']}</td>
          <td>{r['created_at'][:10]}</td>
          <td><span class="status {cls}">{r['status']}</span></td>
        </tr>
        """

    body = f"""
    <div class="card">
      <h2>My Requests</h2>
      <table class="data-table">
        <tr><th>Request</th><th>Service</th><th>Date</th><th>Status</th></tr>
        {body_rows or '<tr><td colspan="4">No requests found.</td></tr>'}
      </table>
    </div>
    """
    return page("My Requests", body)


@app.route("/request/<int:request_id>")
@login_required
def request_detail(request_id):
    row = get_request(request_id)
    if not row:
        abort(404)

    user = current_user()
    if row["user_id"] != user["id"]:
        abort(403)

    data = parse_json(row)
    files = get_request_files(request_id)

    cls = (
        "completed" if row["status"] == "Completed"
        else "processing" if row["status"] == "Processing"
        else "rejected" if row["status"] == "Rejected"
        else "received"
    )

    items = ""
    hidden = {
        "password", "password_hash"
    }
    for k, v in data.items():
        if k in hidden:
            continue
        label = k.replace("_", " ").title()
        items += f"""
        <div class="k">{label}</div>
        <div>{str(v).replace(chr(10), '<br>')}</div>
        """

    file_items = ""
    for f in files:
        file_items += f"""
        <li>
          <a href="/files/{f['stored_name']}" target="_blank">
            {f['original_name']}
          </a>
        </li>
        """

    output = ""
    if row["output_file"]:
        output = f"""
        <section class="card">
          <h2>Completed Result</h2>
          <p>KOJA has uploaded a result for this request.</p>
          <a class="btn green"
             href="/download-result/{row['id']}">
             Download Result
          </a>
        </section>
        """

    body = f"""
    <section class="card">
      <h2>{row['request_no']}</h2>
      <p><strong>Service:</strong> {row['service_name']}</p>
      <p><strong>Status:</strong>
        <span class="status {cls}">{row['status']}</span>
      </p>
      <p class="small">Submitted: {row['created_at']}</p>
    </section>

    <section class="card">
      <h2>Client Information / Request Details</h2>
      <div class="kv">{items}</div>
    </section>

    <section class="card">
      <h2>Documents</h2>
      <ul>{file_items or '<li>No documents attached.</li>'}</ul>
    </section>

    <section class="card">
      <h2>KOJA Response</h2>
      <p>{row['admin_response'] or 'No admin response has been added yet.'}</p>
    </section>

    {output}
    """
    return page(row["request_no"], body)


@app.route("/files/<path:filename>")
@login_required
def private_file(filename):
    # Only allow authenticated clients to access uploaded documents.
    # Admin can also access them.
    if not session.get("user_id") and not session.get("admin_logged_in"):
        abort(403)

    path = UPLOAD_DIR / filename
    if not path.exists() or not path.is_file():
        abort(404)

    return send_from_directory(UPLOAD_DIR, filename, as_attachment=False)


@app.route("/download-result/<int:request_id>")
@login_required
def download_result(request_id):
    row = get_request(request_id)
    if not row:
        abort(404)

    user = current_user()
    if row["user_id"] != user["id"]:
        abort(403)

    if not row["output_file"]:
        abort(404)

    path = UPLOAD_DIR / row["output_file"]
    if not path.exists():
        abort(404)

    download_name = row["output_file_original"] or row["output_file"]
    return send_from_directory(
        UPLOAD_DIR,
        row["output_file"],
        as_attachment=True,
        download_name=download_name
    )


@app.route("/notifications")
@login_required
def notifications():
    user = current_user()
    conn = db()
    rows = conn.execute(
        """
        SELECT * FROM notifications
        WHERE user_id=?
        ORDER BY id DESC
        """,
        (user["id"],)
    ).fetchall()

    conn.execute(
        "UPDATE notifications SET is_read=1 WHERE user_id=?",
        (user["id"],)
    )
    conn.commit()
    conn.close()

    cards = ""
    for n in rows:
        cards += f"""
        <div class="card">
          <h3>{n['title']}</h3>
          <p>{n['message']}</p>
          <div class="small">{n['created_at']}</div>
        </div>
        """

    body = cards or '<div class="card"><h2>Notifications</h2><p>No notifications yet.</p></div>'
    return page("Notifications", body)


@app.route("/profile")
@login_required
def profile():
    user = current_user()
    body = f"""
    <div class="card">
      <h2>Profile</h2>
      <div class="kv">
        <div class="k">Full Name</div><div>{user['full_name']}</div>
        <div class="k">Email</div><div>{user['email']}</div>
        <div class="k">Phone</div><div>{user['phone'] or ''}</div>
        <div class="k">Account Created</div><div>{user['created_at']}</div>
      </div>
    </div>
    """
    return page("Profile", body)


# ============================================================
# ADMIN
# ============================================================

@app.route("/admin")
@admin_required
def admin_dashboard():
    conn = db()
    total = conn.execute(
        "SELECT COUNT(*) c FROM requests"
    ).fetchone()["c"]
    received = conn.execute(
        "SELECT COUNT(*) c FROM requests WHERE status='Request Received'"
    ).fetchone()["c"]
    processing = conn.execute(
        "SELECT COUNT(*) c FROM requests WHERE status='Processing'"
    ).fetchone()["c"]
    completed = conn.execute(
        "SELECT COUNT(*) c FROM requests WHERE status='Completed'"
    ).fetchone()["c"]
    rejected = conn.execute(
        "SELECT COUNT(*) c FROM requests WHERE status='Rejected'"
    ).fetchone()["c"]

    rows = conn.execute(
        """
        SELECT r.*, u.full_name, u.email
        FROM requests r
        JOIN users u ON u.id=r.user_id
        ORDER BY r.id DESC
        LIMIT 100
        """
    ).fetchall()
    conn.close()

    stats = f"""
    <div class="grid">
      <div class="service"><strong>Total</strong><h2>{total}</h2></div>
      <div class="service"><strong>Request Received</strong><h2>{received}</h2></div>
      <div class="service"><strong>Processing</strong><h2>{processing}</h2></div>
      <div class="service"><strong>Completed</strong><h2>{completed}</h2></div>
      <div class="service"><strong>Rejected</strong><h2>{rejected}</h2></div>
    </div>
    """

    trs = ""
    for r in rows:
        cls = (
            "completed" if r["status"] == "Completed"
            else "processing" if r["status"] == "Processing"
            else "rejected" if r["status"] == "Rejected"
            else "received"
        )
        trs += f"""
        <tr>
          <td><a href="/admin/request/{r['id']}"><strong>{r['request_no']}</strong></a></td>
          <td>{r['service_name']}</td>
          <td>{r['full_name']}</td>
          <td>{r['email']}</td>
          <td><span class="status {cls}">{r['status']}</span></td>
        </tr>
        """

    body = f"""
    <section class="hero">
      <h1>Admin Dashboard</h1>
      <p>Manage KOJA service requests separately by service type.</p>
    </section>
    {stats}
    <section class="card">
      <h2>All Requests</h2>
      <table class="data-table">
        <tr>
          <th>Request</th><th>Service</th><th>Client</th>
          <th>Email</th><th>Status</th>
        </tr>
        {trs or '<tr><td colspan="5">No requests.</td></tr>'}
      </table>
    </section>
    """
    return page("Admin Dashboard", body, admin=True)


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if (
            secrets.compare_digest(email, ADMIN_EMAIL) and
            secrets.compare_digest(password, ADMIN_PASSWORD)
        ):
            session.clear()
            session["admin_logged_in"] = True
            return redirect(url_for("admin_dashboard"))

        flash("Invalid administrator credentials.", "error")

    body = f"""
    <div class="card" style="max-width:600px;margin:auto">
      <h2>KOJA Administrator Login</h2>
      <p class="small">This login is separate from client accounts.</p>
      <form method="post">
        <div class="field">
          <label>Admin Email *</label>
          <input type="email" name="email" required>
        </div>
        <div class="field">
          <label>Admin Password *</label>
          <input type="password" name="password" required>
        </div>
        <button class="btn">Admin Login</button>
      </form>
    </div>
    """
    return page("Admin Login", body)


@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("admin_login"))


@app.route("/admin/request/<int:request_id>", methods=["GET", "POST"])
@admin_required
def admin_request_detail(request_id):
    row = get_request(request_id)
    if not row:
        abort(404)

    if request.method == "POST":
        status = request.form.get("status", "").strip()
        response = request.form.get("admin_response", "").strip()

        allowed_statuses = {
            "Request Received",
            "Processing",
            "Completed",
            "Rejected"
        }

        if status not in allowed_statuses:
            flash("Invalid status.", "error")
        else:
            output = request.files.get("result_file")
            output_stored = row["output_file"]
            output_original = row["output_file_original"]

            if output and output.filename:
                if not allowed_file(output.filename):
                    flash("Unsupported result file type.", "error")
                    return redirect(url_for("admin_request_detail", request_id=request_id))

                original = secure_filename(output.filename)
                ext = original.rsplit(".", 1)[1].lower()
                stored = f"result-{uuid.uuid4().hex}.{ext}"
                output.save(UPLOAD_DIR / stored)
                output_stored = stored
                output_original = original

            conn = db()
            conn.execute(
                """
                UPDATE requests
                SET status=?, admin_response=?, output_file=?,
                    output_file_original=?, updated_at=?
                WHERE id=?
                """,
                (
                    status, response,
                    output_stored, output_original,
                    now_iso(), request_id
                )
            )
            conn.commit()
            conn.close()

            add_notification(
                row["user_id"],
                f"Request Updated: {row['request_no']}",
                f"Your {row['service_name']} request is now '{status}'. "
                + (f"KOJA response: {response}" if response else "")
            )

            flash("Request updated successfully.", "success")
            return redirect(url_for("admin_request_detail", request_id=request_id))

    data = parse_json(row)
    files = get_request_files(request_id)

    items = ""
    for k,v in data.items():
        items += f"""
        <div class="k">{k.replace('_',' ').title()}</div>
        <div>{str(v).replace(chr(10), '<br>')}</div>
        """

    file_items = ""
    for f in files:
        file_items += f"""
        <li>
          <a href="/files/{f['stored_name']}" target="_blank">
            {f['original_name']}
          </a>
        </li>
        """

    selected = {}
    for s in ["Request Received","Processing","Completed","Rejected"]:
        selected[s] = "selected" if row["status"] == s else ""

    body = f"""
    <section class="card">
      <h2>{row['request_no']}</h2>
      <p><strong>Service:</strong> {row['service_name']}</p>
      <p><strong>Client:</strong> {row['full_name']}</p>
      <p><strong>Email:</strong> {row['user_email']}</p>
      <p><strong>Phone:</strong> {row['user_phone'] or ''}</p>
    </section>

    <section class="card">
      <h2>Submitted Information</h2>
      <div class="kv">{items}</div>
    </section>

    <section class="card">
      <h2>Client Documents</h2>
      <ul>{file_items or '<li>No documents.</li>'}</ul>
    </section>

    <section class="card">
      <h2>Process Request</h2>
      <form method="post" enctype="multipart/form-data">
        <div class="field">
          <label>Status</label>
          <select name="status">
            <option {selected['Request Received']}>Request Received</option>
            <option {selected['Processing']}>Processing</option>
            <option {selected['Completed']}>Completed</option>
            <option {selected['Rejected']}>Rejected</option>
          </select>
        </div>

        <div class="field">
          <label>Admin Response</label>
          <textarea name="admin_response"
            placeholder="Enter instructions, progress or result message.">{row['admin_response'] or ''}</textarea>
        </div>

        <div class="field filebox">
          <label>Upload Completed Result</label>
          <input type="file" name="result_file"
                 accept=".pdf,.doc,.docx,.jpg,.jpeg,.png,.webp">
          <div class="help">
            Upload the completed PDF/Word/document for the client.
            Maximum 10 MB.
          </div>
        </div>

        <button class="btn green">Save Request Update</button>
      </form>
    </section>

    <a class="btn light" href="/admin">← Back to Admin Dashboard</a>
    """
    return page("Admin Request", body, admin=True)


# ============================================================
# ERROR HANDLERS
# ============================================================

@app.errorhandler(400)
def bad_request(error):
    body = """
    <div class="card">
      <h1>400</h1>
      <p>The request could not be understood. Please go back and try again.</p>
      <a class="btn" href="/">Return Home</a>
    </div>
    """
    return page("400", body), 400


@app.errorhandler(403)
def forbidden(error):
    body = """
    <div class="card">
      <h1>403</h1>
      <p>You do not have permission to access this page.</p>
      <a class="btn" href="/">Return Home</a>
    </div>
    """
    return page("403", body), 403


@app.errorhandler(404)
def not_found(error):
    body = """
    <div class="card">
      <h1>404</h1>
      <p>The page or request could not be found.</p>
      <a class="btn" href="/">Return Home</a>
    </div>
    """
    return page("404", body), 404


@app.errorhandler(413)
def too_large(error):
    body = """
    <div class="card">
      <h1>File Too Large</h1>
      <p>The maximum upload size is 10 MB.</p>
      <a class="btn" href="/">Return Home</a>
    </div>
    """
    return page("File Too Large", body), 413


# ============================================================
# START
# ============================================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)

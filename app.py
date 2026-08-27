import os
import io
import uuid
import secrets
import hashlib
import logging
from datetime import datetime, timezone
from functools import wraps
from html import escape

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
    send_file,
    abort,
)

from reportlab.lib.pagesizes import A4
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.enums import TA_CENTER


# ============================================================
# ENVIRONMENT
# ============================================================

load_dotenv()

SUPABASE_URL = os.getenv(
    "SUPABASE_URL",
    "https://YOUR-PROJECT.supabase.co"
).rstrip("/")

SUPABASE_SERVICE_KEY = os.getenv(
    "SUPABASE_SERVICE_KEY",
    ""
)

SUPABASE_ANON_KEY = os.getenv(
    "SUPABASE_ANON_KEY",
    ""
)

SECRET_KEY = os.getenv(
    "FLASK_SECRET_KEY",
    secrets.token_hex(32)
)

APP_NAME = "KOJA AFRICA"
APP_TAGLINE = "Assignment Questions • Academic Answers • Learning Resources"

STORAGE_BUCKET = os.getenv(
    "SUPABASE_STORAGE_BUCKET",
    "koja-assignments"
)

MAX_FILE_SIZE = 10 * 1024 * 1024

ADMIN_UUID = os.getenv(
    "ADMIN_UUID",
    "fea4ac9a-97a1-4fcf-b5cb-870843dc48dd"
)


# ============================================================
# FLASK
# ============================================================

app = Flask(__name__)

app.secret_key = SECRET_KEY

app.config["MAX_CONTENT_LENGTH"] = MAX_FILE_SIZE

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)


# ============================================================
# SUPABASE REST
# ============================================================

def supabase_headers(use_service=True):
    key = SUPABASE_SERVICE_KEY if use_service else SUPABASE_ANON_KEY

    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }


def supabase_request(
    method,
    table,
    params=None,
    json_data=None,
    use_service=True,
    headers_extra=None
):
    url = f"{SUPABASE_URL}/rest/v1/{table}"

    headers = supabase_headers(use_service)

    if headers_extra:
        headers.update(headers_extra)

    try:
        response = requests.request(
            method,
            url,
            headers=headers,
            params=params,
            json=json_data,
            timeout=25
        )

        if not response.ok:
            logging.error(
                "Supabase error %s: %s",
                response.status_code,
                response.text
            )

        return response

    except requests.RequestException as exc:
        logging.error("Supabase connection error: %s", exc)
        return None


def supabase_rpc(function_name, payload=None):
    url = f"{SUPABASE_URL}/rest/v1/rpc/{function_name}"

    try:
        response = requests.post(
            url,
            headers=supabase_headers(True),
            json=payload or {},
            timeout=25
        )

        if not response.ok:
            logging.error(
                "RPC error %s: %s",
                response.status_code,
                response.text
            )

        return response

    except requests.RequestException as exc:
        logging.error("RPC connection error: %s", exc)
        return None


# ============================================================
# DATABASE HELPERS
# ============================================================

def db_select(
    table,
    filters=None,
    select="*",
    order=None,
    limit=None
):
    params = {
        "select": select
    }

    if filters:
        params.update(filters)

    if order:
        params["order"] = order

    if limit:
        params["limit"] = str(limit)

    response = supabase_request(
        "GET",
        table,
        params=params
    )

    if not response or not response.ok:
        return []

    try:
        return response.json()
    except Exception:
        return []


def db_insert(table, data, returning=True):
    headers_extra = {}

    if returning:
        headers_extra["Prefer"] = "return=representation"
    else:
        headers_extra["Prefer"] = "return=minimal"

    response = supabase_request(
        "POST",
        table,
        json_data=data,
        headers_extra=headers_extra
    )

    if not response or not response.ok:
        return []

    try:
        return response.json()
    except Exception:
        return []


def db_update(table, filters, data, returning=True):
    headers_extra = {}

    if returning:
        headers_extra["Prefer"] = "return=representation"
    else:
        headers_extra["Prefer"] = "return=minimal"

    response = supabase_request(
        "PATCH",
        table,
        params=filters,
        json_data=data,
        headers_extra=headers_extra
    )

    if not response or not response.ok:
        return []

    try:
        return response.json()
    except Exception:
        return []


def db_delete(table, filters):
    response = supabase_request(
        "DELETE",
        table,
        params=filters,
        headers_extra={"Prefer": "return=minimal"}
    )

    return bool(response and response.ok)


# ============================================================
# PASSWORD SECURITY
# ============================================================

def hash_password(password):
    salt = secrets.token_bytes(16)

    password_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        210000
    )

    return (
        salt.hex()
        + "$"
        + password_hash.hex()
    )


def verify_password(password, stored):
    try:
        salt_hex, hash_hex = stored.split("$", 1)

        salt = bytes.fromhex(salt_hex)

        calculated = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            210000
        )

        return secrets.compare_digest(
            calculated.hex(),
            hash_hex
        )

    except Exception:
        return False


# ============================================================
# SESSION
# ============================================================

def current_user():
    user_id = session.get("user_id")

    if not user_id:
        return None

    users = db_select(
        "profiles",
        filters={
            "id": f"eq.{user_id}"
        },
        limit=1
    )

    return users[0] if users else None


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):

        if not session.get("user_id"):
            flash("Please log in first.", "warning")
            return redirect(url_for("login"))

        return view(*args, **kwargs)

    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):

        user = current_user()

        if not user:
            return redirect(url_for("login"))

        if user.get("role") != "admin":
            abort(403)

        return view(*args, **kwargs)

    return wrapped


# ============================================================
# ACTIVITY LOG
# ============================================================

def log_activity(action, description=""):
    user_id = session.get("user_id")

    if not user_id:
        return

    data = {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "action": action,
        "description": description,
        "created_at": datetime.now(timezone.utc).isoformat()
    }

    try:
        db_insert(
            "activity_logs",
            data,
            returning=False
        )
    except Exception as exc:
        logging.warning(
            "Activity log failed: %s",
            exc
        )


# ============================================================
# STORAGE
# ============================================================

def upload_storage(file_bytes, filename, content_type):
    safe_name = filename.replace("/", "_").replace("\\", "_")

    path = (
        f"documents/"
        f"{uuid.uuid4()}/"
        f"{safe_name}"
    )

    url = (
        f"{SUPABASE_URL}/storage/v1/object/"
        f"{STORAGE_BUCKET}/{path}"
    )

    headers = supabase_headers(True)

    headers["Content-Type"] = content_type or "application/octet-stream"

    try:
        response = requests.post(
            url,
            headers=headers,
            data=file_bytes,
            timeout=60
        )

        if not response.ok:
            logging.error(
                "Storage upload failed: %s",
                response.text
            )
            return None

        return path

    except requests.RequestException as exc:
        logging.error(
            "Storage connection error: %s",
            exc
        )
        return None


def download_storage(path):
    url = (
        f"{SUPABASE_URL}/storage/v1/object/"
        f"{STORAGE_BUCKET}/{path}"
    )

    try:
        response = requests.get(
            url,
            headers=supabase_headers(True),
            timeout=60
        )

        if not response.ok:
            return None

        return response.content

    except requests.RequestException:
        return None


# ============================================================
# PDF GENERATION
# ============================================================

def create_pdf(title, body, metadata=None):
    buffer = io.BytesIO()

    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=45,
        leftMargin=45,
        topMargin=45,
        bottomMargin=45
    )

    styles = getSampleStyleSheet()

    title_style = styles["Title"]
    title_style.alignment = TA_CENTER

    normal = styles["BodyText"]
    normal.leading = 17

    story = []

    story.append(
        Paragraph(
            escape(APP_NAME),
            title_style
        )
    )

    story.append(
        Spacer(1, 10)
    )

    story.append(
        Paragraph(
            escape(title),
            styles["Heading2"]
        )
    )

    story.append(
        Spacer(1, 12)
    )

    if metadata:

        rows = []

        for key, value in metadata.items():
            rows.append([
                Paragraph(
                    escape(str(key)),
                    styles["BodyText"]
                ),
                Paragraph(
                    escape(str(value)),
                    styles["BodyText"]
                )
            ])

        table = Table(
            rows,
            colWidths=[120, 350]
        )

        table.setStyle(
            TableStyle([
                (
                    "GRID",
                    (0, 0),
                    (-1, -1),
                    0.5,
                    colors.grey
                ),
                (
                    "VALIGN",
                    (0, 0),
                    (-1, -1),
                    "TOP"
                ),
                (
                    "BOTTOMPADDING",
                    (0, 0),
                    (-1, -1),
                    6
                ),
                (
                    "TOPPADDING",
                    (0, 0),
                    (-1, -1),
                    6
                )
            ])
        )

        story.append(table)

        story.append(
            Spacer(1, 15)
        )

    for paragraph in body.split("\n"):

        if paragraph.strip():

            story.append(
                Paragraph(
                    escape(paragraph),
                    normal
                )
            )

            story.append(
                Spacer(1, 7)
            )

    story.append(
        Spacer(1, 20)
    )

    story.append(
        Paragraph(
            "Generated by KOJA AFRICA",
            styles["Italic"]
        )
    )

    document.build(story)

    buffer.seek(0)

    return buffer


# ============================================================
# HTML
# ============================================================

BASE_HTML = """
<!doctype html>
<html>
<head>

<meta name="viewport"
      content="width=device-width, initial-scale=1">

<title>{{ title or "KOJA AFRICA" }}</title>

<style>

* {
    box-sizing: border-box;
}

body {
    margin: 0;
    font-family:
        Arial,
        Helvetica,
        sans-serif;
    background: #f4f7fb;
    color: #172033;
}

nav {
    background: #071d49;
    color: white;
    padding: 15px 5%;
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 15px;
    flex-wrap: wrap;
}

.brand {
    font-size: 22px;
    font-weight: 800;
    letter-spacing: .5px;
}

.navlinks {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
}

.navlinks a {
    color: white;
    text-decoration: none;
    padding: 9px 12px;
    border-radius: 8px;
}

.navlinks a:hover {
    background: rgba(255,255,255,.12);
}

.container {
    width: 92%;
    max-width: 1180px;
    margin: 30px auto;
}

.hero {
    background:
        linear-gradient(
            135deg,
            #071d49,
            #0b397f
        );
    color: white;
    border-radius: 18px;
    padding: 45px 30px;
    margin-bottom: 25px;
}

.hero h1 {
    font-size: 38px;
    margin: 0 0 12px;
}

.hero p {
    font-size: 17px;
    line-height: 1.6;
    max-width: 750px;
}

.card {
    background: white;
    border-radius: 15px;
    padding: 22px;
    margin-bottom: 20px;
    box-shadow:
        0 5px 22px
        rgba(20,40,80,.07);
}

.grid {
    display: grid;
    grid-template-columns:
        repeat(auto-fit,minmax(230px,1fr));
    gap: 18px;
}

.stat {
    font-size: 30px;
    font-weight: 800;
    color: #0b397f;
}

input,
textarea,
select {
    width: 100%;
    padding: 12px;
    border: 1px solid #d6dce8;
    border-radius: 9px;
    margin-top: 6px;
    margin-bottom: 14px;
    font-size: 15px;
}

textarea {
    min-height: 130px;
    resize: vertical;
}

button,
.btn {
    display: inline-block;
    border: 0;
    background: #0b397f;
    color: white;
    padding: 11px 16px;
    border-radius: 9px;
    text-decoration: none;
    cursor: pointer;
    font-weight: 700;
}

.btn-green {
    background: #168653;
}

.btn-red {
    background: #b3261e;
}

.btn-light {
    background: #e9eef7;
    color: #172033;
}

.badge {
    display: inline-block;
    padding: 5px 9px;
    border-radius: 20px;
    background: #e8eef8;
    font-size: 12px;
    font-weight: 700;
}

.badge-paid {
    background: #fff1c7;
    color: #7a5500;
}

.badge-free {
    background: #dff7e9;
    color: #11643b;
}

.flash {
    padding: 12px;
    background: #fff4d6;
    border-radius: 9px;
    margin-bottom: 15px;
}

.question {
    border-left: 4px solid #0b397f;
    padding-left: 15px;
}

.small {
    color: #687386;
    font-size: 13px;
}

footer {
    text-align: center;
    color: #718096;
    padding: 35px;
}

@media(max-width:700px) {

    .hero h1 {
        font-size: 29px;
    }

    nav {
        align-items: flex-start;
    }

}

</style>

</head>

<body>

<nav>

<div class="brand">
KOJA AFRICA
</div>

<div class="navlinks">

<a href="{{ url_for('home') }}">Home</a>

{% if session.get("user_id") %}
<a href="{{ url_for('dashboard') }}">
Dashboard
</a>

<a href="{{ url_for('documents') }}">
Documents
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

<div class="container">

{% with messages = get_flashed_messages() %}

{% for message in messages %}

<div class="flash">
{{ message }}
</div>

{% endfor %}

{% endwith %}

{{ content|safe }}

</div>

<footer>
KOJA AFRICA © 2026 —
Knowledge • Questions • Answers
</footer>

</body>
</html>
"""


def page(content, title="KOJA AFRICA"):
    return render_template_string(
        BASE_HTML,
        content=content,
        title=title
    )


# ============================================================
# HOME
# ============================================================

@app.route("/")
def home():

    content = """
    <section class="hero">

        <h1>Learn. Ask. Discover.</h1>

        <p>
        KOJA AFRICA is a digital academic platform
        connecting students with academic questions,
        answers and learning resources.
        </p>

        <a class="btn"
           href="/register">
           Create Account
        </a>

        <a class="btn btn-light"
           href="/login">
           Login
        </a>

    </section>

    <div class="grid">

        <div class="card">
            <h3>Ask Questions</h3>
            <p>
            Submit academic questions and receive
            structured answers.
            </p>
        </div>

        <div class="card">
            <h3>Learning Resources</h3>
            <p>
            Access a growing library of academic
            documents and resources.
            </p>
        </div>

        <div class="card">
            <h3>Digital Documents</h3>
            <p>
            Receive, read and securely download
            documents.
            </p>
        </div>

        <div class="card">
            <h3>Future Marketplace</h3>
            <p>
            KOJA is structured to support free
            and premium educational resources.
            </p>
        </div>

    </div>
    """

    return page(content)


# ============================================================
# REGISTER
# ============================================================

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not name or not email or not password:
            flash("Complete all fields.")
            return redirect(url_for("register"))

        if len(password) < 8:
            flash("Password must contain at least 8 characters.")
            return redirect(url_for("register"))

        existing = db_select(
            "profiles",
            filters={
                "email": f"eq.{email}"
            },
            limit=1
        )

        if existing:
            flash("An account with that email already exists.")
            return redirect(url_for("login"))

        user_id = str(uuid.uuid4())

        password_hash = hash_password(password)

        user_data = {
            "id": user_id,
            "name": name,
            "email": email,
            "password_hash": password_hash,
            "role": "student",
            "created_at":
                datetime.now(timezone.utc).isoformat()
        }

        result = db_insert(
            "profiles",
            user_data
        )

        if not result:
            flash(
                "Registration failed. Check your Supabase table."
            )
            return redirect(url_for("register"))

        session.clear()

        session["user_id"] = user_id

        log_activity(
            "registration",
            "New student account created."
        )

        flash("Account created successfully.")

        return redirect(url_for("dashboard"))

    content = """
    <div class="card">

        <h2>Create Student Account</h2>

        <form method="POST">

            <label>Full name</label>
            <input
                name="name"
                required
            >

            <label>Email</label>
            <input
                type="email"
                name="email"
                required
            >

            <label>Password</label>
            <input
                type="password"
                name="password"
                minlength="8"
                required
            >

            <button type="submit">
                Create Account
            </button>

        </form>

    </div>
    """

    return page(content, "Create Account")


# ============================================================
# LOGIN
# ============================================================

@app.route("/login", methods=["GET", "POST"])
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

        users = db_select(
            "profiles",
            filters={
                "email": f"eq.{email}"
            },
            limit=1
        )

        if not users:
            flash("Invalid email or password.")
            return redirect(url_for("login"))

        user = users[0]

        if not verify_password(
            password,
            user.get("password_hash", "")
        ):
            flash("Invalid email or password.")
            return redirect(url_for("login"))

        session.clear()

        session["user_id"] = user["id"]

        session["role"] = user.get(
            "role",
            "student"
        )

        log_activity(
            "login",
            "User logged in."
        )

        return redirect(url_for("dashboard"))

    content = """
    <div class="card">

        <h2>Login</h2>

        <form method="POST">

            <label>Email</label>

            <input
                type="email"
                name="email"
                required
            >

            <label>Password</label>

            <input
                type="password"
                name="password"
                required
            >

            <button type="submit">
                Login
            </button>

        </form>

    </div>
    """

    return page(content, "Login")


# ============================================================
# LOGOUT
# ============================================================

@app.route("/logout")
def logout():

    if session.get("user_id"):
        log_activity(
            "logout",
            "User logged out."
        )

    session.clear()

    flash("You have been logged out.")

    return redirect(url_for("home"))


# ============================================================
# DASHBOARD
# ============================================================

@app.route("/dashboard")
@login_required
def dashboard():

    user = current_user()

    if not user:
        session.clear()
        return redirect(url_for("login"))

    if user.get("role") == "admin":
        return redirect(url_for("admin_dashboard"))

    questions = db_select(
        "questions",
        filters={
            "student_id":
                f"eq.{user['id']}"
        },
        order="created_at.desc",
        limit=10
    )

    documents = db_select(
        "documents",
        filters={
            "recipient_id":
                f"eq.{user['id']}"
        },
        order="created_at.desc",
        limit=10
    )

    unread = sum(
        1 for d in documents
        if not d.get("is_read", False)
    )

    content = f"""
    <section class="hero">

        <h1>
        Welcome, {escape(user.get("name", "Student"))}
        </h1>

        <p>
        Your KOJA AFRICA academic dashboard.
        </p>

        <a class="btn"
           href="/questions/new">
           Ask a Question
        </a>

        <a class="btn btn-light"
           href="/documents">
           Open Documents
        </a>

    </section>

    <div class="grid">

        <div class="card">
            <div class="stat">
                {len(questions)}
            </div>
            <div>Recent Questions</div>
        </div>

        <div class="card">
            <div class="stat">
                {len(documents)}
            </div>
            <div>Documents</div>
        </div>

        <div class="card">
            <div class="stat">
                {unread}
            </div>
            <div>Unread Documents</div>
        </div>

    </div>

    <div class="card">

        <h2>My Questions</h2>
    """

    if questions:

        for q in questions:

            content += f"""
            <div class="question">
                <h3>
                    {escape(q.get("subject", "Question"))}
                </h3>

                <p>
                    {escape(q.get("question", ""))}
                </p>

                <span class="badge">
                    {escape(q.get("status", "pending"))}
                </span>
            </div>
            <hr>
            """

    else:

        content += """
        <p>No questions submitted yet.</p>
        """

    content += "</div>"

    return page(content, "Dashboard")


# ============================================================
# NEW QUESTION
# ============================================================

@app.route("/questions/new", methods=["GET", "POST"])
@login_required
def new_question():

    if request.method == "POST":

        subject = request.form.get(
            "subject",
            ""
        ).strip()

        question = request.form.get(
            "question",
            ""
        ).strip()

        if not subject or not question:
            flash("Enter the subject and question.")
            return redirect(url_for("new_question"))

        data = {
            "id": str(uuid.uuid4()),
            "student_id": session["user_id"],
            "subject": subject,
            "question": question,
            "status": "pending",
            "created_at":
                datetime.now(timezone.utc).isoformat()
        }

        result = db_insert(
            "questions",
            data
        )

        if result:

            log_activity(
                "question_created",
                subject
            )

            flash("Question submitted successfully.")

            return redirect(
                url_for("dashboard")
            )

        flash("Unable to submit question.")

    content = """
    <div class="card">

        <h2>Ask KOJA</h2>

        <form method="POST">

            <label>Subject</label>

            <input
                name="subject"
                placeholder="e.g. Chemistry"
                required
            >

            <label>Question</label>

            <textarea
                name="question"
                placeholder="Enter your academic question..."
                required
            ></textarea>

            <button type="submit">
                Submit Question
            </button>

        </form>

    </div>
    """

    return page(content, "Ask Question")


# ============================================================
# QUESTIONS
# ============================================================

@app.route("/questions")
@login_required
def questions():

    user = current_user()

    if user and user.get("role") == "admin":
        return redirect(url_for("admin_questions"))

    rows = db_select(
        "questions",
        filters={
            "student_id":
                f"eq.{session['user_id']}"
        },
        order="created_at.desc"
    )

    content = """
    <div class="card">

        <h2>My Questions</h2>

        <a class="btn"
           href="/questions/new">
           New Question
        </a>

    </div>
    """

    for q in rows:

        answer = q.get("answer") or ""

        content += f"""
        <div class="card">

            <h3>
            {escape(q.get("subject", ""))}
            </h3>

            <p>
            {escape(q.get("question", ""))}
            </p>

            <span class="badge">
            {escape(q.get("status", "pending"))}
            </span>

            <h4>Answer</h4>

            <p>
            {escape(answer) if answer else
            "Awaiting academic answer."}
            </p>

        </div>
        """

    return page(content, "My Questions")


# ============================================================
# DOCUMENTS
# ============================================================

@app.route("/documents")
@login_required
def documents():

    user = current_user()

    if user and user.get("role") == "admin":

        rows = db_select(
            "documents",
            order="created_at.desc"
        )

    else:

        rows = db_select(
            "documents",
            filters={
                "recipient_id":
                    f"eq.{session['user_id']}"
            },
            order="created_at.desc"
        )

    search = request.args.get(
        "q",
        ""
    ).strip().lower()

    if search:

        rows = [
            row for row in rows
            if search in (
                str(row.get("title", ""))
                + " "
                + str(row.get("description", ""))
            ).lower()
        ]

    content = """
    <div class="card">

        <h2>KOJA Document Library</h2>

        <form method="GET">

            <input
                name="q"
                placeholder="Search documents..."
            >

            <button>
                Search
            </button>

        </form>

    </div>
    """

    if not rows:

        content += """
        <div class="card">
            <p>No documents found.</p>
        </div>
        """

    for doc in rows:

        price = doc.get("price", 0) or 0

        is_paid = float(price) > 0

        is_read = doc.get(
            "is_read",
            False
        )

        status = doc.get(
            "status",
            "sent"
        )

        badge = (
            '<span class="badge badge-paid">PAID</span>'
            if is_paid
            else
            '<span class="badge badge-free">FREE</span>'
        )

        content += f"""
        <div class="card">

            <h3>
            {escape(doc.get("title", "Document"))}
            </h3>

            {badge}

            <p>
            {escape(doc.get("description", ""))}
            </p>

            <p class="small">
            Status: {escape(status)}
            |
            {"Read" if is_read else "Unread"}
            </p>

            <a class="btn"
               href="/documents/{doc.get('id')}">
               Open
            </a>

        </div>
        """

    return page(content, "Documents")


# ============================================================
# DOCUMENT VIEW
# ============================================================

@app.route("/documents/<document_id>")
@login_required
def document_view(document_id):

    rows = db_select(
        "documents",
        filters={
            "id": f"eq.{document_id}"
        },
        limit=1
    )

    if not rows:
        abort(404)

    document = rows[0]

    user = current_user()

    is_admin = (
        user and
        user.get("role") == "admin"
    )

    if not is_admin:

        if document.get("recipient_id") != session["user_id"]:
            abort(403)

    price = document.get("price", 0) or 0

    content = f"""
    <div class="card">

        <h2>
        {escape(document.get("title", "Document"))}
        </h2>

        <p>
        {escape(document.get("description", ""))}
        </p>

        <p>
        Price:
        <strong>
        K{float(price):.2f}
        </strong>
        </p>

        <p>
        Status:
        <span class="badge">
        {escape(document.get("status", "sent"))}
        </span>
        </p>
    """

    if not is_admin:

        content += f"""
        <div style="margin-top:20px">

            <a class="btn btn-green"
               href="/documents/{document_id}/received">
               Mark as Received
            </a>

            <a class="btn"
               href="/documents/{document_id}/read">
               Mark as Read
            </a>

            <a class="btn btn-light"
               href="/documents/{document_id}/download">
               Download
            </a>

        </div>
        """

    else:

        content += f"""
        <div style="margin-top:20px">

            <a class="btn"
               href="/documents/{document_id}/download">
               Download
            </a>

        </div>
        """

    content += "</div>"

    return page(content, "Document")


# ============================================================
# SECURE MARK RECEIVED
# ============================================================

@app.route("/documents/<document_id>/received")
@login_required
def mark_received(document_id):

    response = supabase_rpc(
        "mark_document_received",
        {
            "document_uuid": document_id
        }
    )

    if response and response.ok:

        log_activity(
            "document_received",
            document_id
        )

        flash("Document marked as received.")

    else:

        flash(
            "Unable to mark document as received."
        )

    return redirect(
        url_for(
            "document_view",
            document_id=document_id
        )
    )


# ============================================================
# SECURE MARK READ
# ============================================================

@app.route("/documents/<document_id>/read")
@login_required
def mark_read(document_id):

    response = supabase_rpc(
        "mark_document_read",
        {
            "document_uuid": document_id
        }
    )

    if response and response.ok:

        log_activity(
            "document_read",
            document_id
        )

        flash("Document marked as read.")

    else:

        flash(
            "Unable to mark document as read."
        )

    return redirect(
        url_for(
            "document_view",
            document_id=document_id
        )
    )


# ============================================================
# DOCUMENT DOWNLOAD
# ============================================================

@app.route("/documents/<document_id>/download")
@login_required
def download_document(document_id):

    rows = db_select(
        "documents",
        filters={
            "id": f"eq.{document_id}"
        },
        limit=1
    )

    if not rows:
        abort(404)

    document = rows[0]

    user = current_user()

    is_admin = (
        user and
        user.get("role") == "admin"
    )

    if not is_admin:

        if document.get("recipient_id") != session["user_id"]:
            abort(403)

    price = float(
        document.get("price", 0) or 0
    )

    # --------------------------------------------------------
    # Future payment gate
    # --------------------------------------------------------
    #
    # For now, free documents download normally.
    #
    # Paid documents are intentionally blocked until
    # a payment record confirms access.
    #

    if price > 0 and not is_admin:

        purchases = db_select(
            "purchases",
            filters={
                "document_id":
                    f"eq.{document_id}",
                "user_id":
                    f"eq.{session['user_id']}",
                "status":
                    "eq.completed"
            },
            limit=1
        )

        if not purchases:

            flash(
                "This document requires payment before download."
            )

            return redirect(
                url_for(
                    "document_view",
                    document_id=document_id
                )
            )

    path = document.get(
        "storage_path"
    )

    if not path:
        abort(404)

    file_bytes = download_storage(path)

    if not file_bytes:
        flash("Unable to download document.")
        return redirect(
            url_for(
                "document_view",
                document_id=document_id
            )
        )

    # Download tracking
    db_insert(
        "document_downloads",
        {
            "id": str(uuid.uuid4()),
            "document_id": document_id,
            "user_id": session["user_id"],
            "created_at":
                datetime.now(timezone.utc).isoformat()
        },
        returning=False
    )

    log_activity(
        "document_download",
        document.get("title", "")
    )

    filename = document.get(
        "filename",
        "document"
    )

    return send_file(
        io.BytesIO(file_bytes),
        as_attachment=True,
        download_name=filename,
        mimetype=document.get(
            "mime_type",
            "application/octet-stream"
        )
    )


# ============================================================
# ADMIN DASHBOARD
# ============================================================

@app.route("/admin")
@admin_required
def admin_dashboard():

    users = db_select(
        "profiles",
        select="id,name,email,role,created_at",
        order="created_at.desc"
    )

    questions = db_select(
        "questions",
        order="created_at.desc"
    )

    documents = db_select(
        "documents",
        order="created_at.desc"
    )

    purchases = db_select(
        "purchases",
        order="created_at.desc"
    )

    content = """
    <section class="hero">

        <h1>Admin Control Centre</h1>

        <p>
        KOJA AFRICA administration, academic
        content and digital document management.
        </p>

    </section>

    <div class="grid">

        <div class="card">
            <div class="stat">
    """ + str(len(users)) + """
            </div>
            Users
        </div>

        <div class="card">
            <div class="stat">
    """ + str(len(questions)) + """
            </div>
            Questions
        </div>

        <div class="card">
            <div class="stat">
    """ + str(len(documents)) + """
            </div>
            Documents
        </div>

        <div class="card">
            <div class="stat">
    """ + str(len(purchases)) + """
            </div>
            Purchases
        </div>

    </div>

    <div class="grid">

        <div class="card">
            <h3>Academic Management</h3>

            <a class="btn"
               href="/admin/questions">
               Questions
            </a>
        </div>

        <div class="card">
            <h3>Document Management</h3>

            <a class="btn"
               href="/admin/documents">
               Upload Documents
            </a>
        </div>

        <div class="card">
            <h3>Users</h3>

            <a class="btn"
               href="/admin/users">
               Manage Users
            </a>
        </div>

        <div class="card">
            <h3>Activity</h3>

            <a class="btn"
               href="/admin/logs">
               View Logs
            </a>
        </div>

    </div>
    """

    return page(content, "Admin")


# ============================================================
# ADMIN QUESTIONS
# ============================================================

@app.route("/admin/questions")
@admin_required
def admin_questions():

    rows = db_select(
        "questions",
        order="created_at.desc"
    )

    content = """
    <div class="card">

        <h2>Student Questions</h2>

    </div>
    """

    for q in rows:

        content += f"""
        <div class="card">

            <h3>
            {escape(q.get("subject", ""))}
            </h3>

            <p>
            {escape(q.get("question", ""))}
            </p>

            <span class="badge">
            {escape(q.get("status", "pending"))}
            </span>

            <br><br>

            <a class="btn"
               href="/admin/questions/{q.get('id')}">
               Open & Answer
            </a>

        </div>
        """

    return page(content, "Admin Questions")


# ============================================================
# ADMIN ANSWER
# ============================================================

@app.route(
    "/admin/questions/<question_id>",
    methods=["GET", "POST"]
)
@admin_required
def admin_question(question_id):

    rows = db_select(
        "questions",
        filters={
            "id": f"eq.{question_id}"
        },
        limit=1
    )

    if not rows:
        abort(404)

    question = rows[0]

    if request.method == "POST":

        answer = request.form.get(
            "answer",
            ""
        ).strip()

        status = (
            "answered"
            if answer
            else "pending"
        )

        result = db_update(
            "questions",
            {
                "id":
                    f"eq.{question_id}"
            },
            {
                "answer": answer,
                "status": status,
                "answered_by":
                    session["user_id"],
                "answered_at":
                    datetime.now(timezone.utc).isoformat()
            }
        )

        if result:

            log_activity(
                "question_answered",
                question_id
            )

            # Optional notification
            try:

                db_insert(
                    "notifications",
                    {
                        "id": str(uuid.uuid4()),
                        "user_id":
                            question.get("student_id"),
                        "title":
                            "Your question has been answered",
                        "message":
                            question.get("subject", ""),
                        "is_read": False,
                        "created_at":
                            datetime.now(
                                timezone.utc
                            ).isoformat()
                    },
                    returning=False
                )

            except Exception:
                pass

            flash("Answer saved.")

            return redirect(
                url_for(
                    "admin_questions"
                )
            )

        flash("Unable to save answer.")

    content = f"""
    <div class="card">

        <h2>
        {escape(question.get("subject", ""))}
        </h2>

        <p>
        {escape(question.get("question", ""))}
        </p>

        <form method="POST">

            <label>Academic Answer</label>

            <textarea
                name="answer"
                required
            >{escape(question.get("answer") or "")}</textarea>

            <button>
                Save Answer
            </button>

        </form>

    </div>
    """

    return page(content, "Answer Question")


# ============================================================
# ADMIN DOCUMENTS
# ============================================================

@app.route(
    "/admin/documents",
    methods=["GET", "POST"]
)
@admin_required
def admin_documents():

    if request.method == "POST":

        uploaded = request.files.get(
            "file"
        )

        title = request.form.get(
            "title",
            ""
        ).strip()

        description = request.form.get(
            "description",
            ""
        ).strip()

        recipient_id = request.form.get(
            "recipient_id",
            ""
        ).strip()

        price_raw = request.form.get(
            "price",
            "0"
        ).strip()

        try:
            price = float(price_raw or 0)
        except ValueError:
            price = 0

        if not uploaded or not title:
            flash(
                "Title and document are required."
            )
            return redirect(
                url_for("admin_documents")
            )

        file_bytes = uploaded.read()

        if len(file_bytes) > MAX_FILE_SIZE:
            flash("File is too large.")
            return redirect(
                url_for("admin_documents")
            )

        storage_path = upload_storage(
            file_bytes,
            uploaded.filename,
            uploaded.content_type
        )

        if not storage_path:
            flash(
                "Document upload failed."
            )
            return redirect(
                url_for("admin_documents")
            )

        document_data = {
            "id": str(uuid.uuid4()),
            "title": title,
            "description": description,
            "filename": uploaded.filename,
            "mime_type":
                uploaded.content_type,
            "storage_path":
                storage_path,
            "price": price,
            "is_paid": price > 0,
            "status": "sent",
            "is_read": False,
            "created_by":
                session["user_id"],
            "created_at":
                datetime.now(
                    timezone.utc
                ).isoformat()
        }

        if recipient_id:
            document_data["recipient_id"] = recipient_id

        result = db_insert(
            "documents",
            document_data
        )

        if result:

            if recipient_id:

                try:

                    db_insert(
                        "notifications",
                        {
                            "id":
                                str(uuid.uuid4()),
                            "user_id":
                                recipient_id,
                            "title":
                                "New document received",
                            "message":
                                title,
                            "is_read":
                                False,
                            "created_at":
                                datetime.now(
                                    timezone.utc
                                ).isoformat()
                        },
                        returning=False
                    )

                except Exception:
                    pass

            log_activity(
                "document_uploaded",
                title
            )

            flash(
                "Document uploaded successfully."
            )

        else:

            flash(
                "Document record could not be created."
            )

    users = db_select(
        "profiles",
        filters={
            "role": "eq.student"
        },
        select="id,name,email",
        order="name.asc"
    )

    docs = db_select(
        "documents",
        order="created_at.desc"
    )

    options = ""

    for user in users:

        options += f"""
        <option value="{user.get("id")}">
        {escape(user.get("name", ""))}
        — {escape(user.get("email", ""))}
        </option>
        """

    content = f"""
    <div class="card">

        <h2>Upload Academic Document</h2>

        <form
            method="POST"
            enctype="multipart/form-data"
        >

            <label>Title</label>

            <input
                name="title"
                required
            >

            <label>Description</label>

            <textarea
                name="description"
            ></textarea>

            <label>Recipient</label>

            <select name="recipient_id">

                <option value="">
                General Library
                </option>

                {options}

            </select>

            <label>
            Price in Zambian Kwacha
            </label>

            <input
                type="number"
                name="price"
                min="0"
                step="0.01"
                value="0"
            >

            <label>File</label>

            <input
                type="file"
                name="file"
                required
            >

            <button>
                Upload Document
            </button>

        </form>

    </div>

    <div class="card">

        <h2>Uploaded Documents</h2>

    """

    for doc in docs:

        content += f"""
        <div>
            <strong>
            {escape(doc.get("title", ""))}
            </strong>

            —
            K{float(doc.get("price", 0) or 0):.2f}

            <span class="badge">
            {escape(doc.get("status", ""))}
            </span>
        </div>

        <hr>
        """

    content += "</div>"

    return page(content, "Admin Documents")


# ============================================================
# ADMIN USERS
# ============================================================

@app.route("/admin/users")
@admin_required
def admin_users():

    users = db_select(
        "profiles",
        select="id,name,email,role,created_at",
        order="created_at.desc"
    )

    content = """
    <div class="card">

        <h2>Registered Users</h2>

    """

    for user in users:

        content += f"""
        <div class="card">

            <strong>
            {escape(user.get("name", ""))}
            </strong>

            <p>
            {escape(user.get("email", ""))}
            </p>

            <span class="badge">
            {escape(user.get("role", ""))}
            </span>

        </div>
        """

    content += "</div>"

    return page(content, "Users")


# ============================================================
# ADMIN LOGS
# ============================================================

@app.route("/admin/logs")
@admin_required
def admin_logs():

    logs = db_select(
        "activity_logs",
        order="created_at.desc",
        limit=200
    )

    content = """
    <div class="card">

        <h2>System Activity Logs</h2>

        <p class="small">
        Visible to administrators only.
        </p>

    </div>
    """

    for log in logs:

        content += f"""
        <div class="card">

            <strong>
            {escape(log.get("action", ""))}
            </strong>

            <p>
            {escape(log.get("description", ""))}
            </p>

            <span class="small">
            {escape(str(log.get("created_at", "")))}
            </span>

        </div>
        """

    return page(content, "Admin Logs")


# ============================================================
# GENERATE QUESTION PDF
# ============================================================

@app.route(
    "/questions/<question_id>/pdf"
)
@login_required
def question_pdf(question_id):

    rows = db_select(
        "questions",
        filters={
            "id": f"eq.{question_id}"
        },
        limit=1
    )

    if not rows:
        abort(404)

    question = rows[0]

    user = current_user()

    if (
        user.get("role") != "admin"
        and question.get("student_id")
        != session["user_id"]
    ):
        abort(403)

    body = (
        "Question:\n"
        + question.get("question", "")
        + "\n\n"
        + "Answer:\n"
        + (
            question.get("answer")
            or
            "No answer available yet."
        )
    )

    pdf = create_pdf(
        question.get(
            "subject",
            "Academic Question"
        ),
        body,
        {
            "Status":
                question.get(
                    "status",
                    ""
                )
        }
    )

    log_activity(
        "question_pdf",
        question_id
    )

    return send_file(
        pdf,
        as_attachment=True,
        download_name="koja-answer.pdf",
        mimetype="application/pdf"
    )


# ============================================================
# HEALTH CHECK
# ============================================================

@app.route("/health")
def health():

    return {
        "app": APP_NAME,
        "status": "online",
        "year": 2026
    }


# ============================================================
# ERROR HANDLERS
# ============================================================

@app.errorhandler(403)
def forbidden(error):

    return page(
        """
        <div class="card">
            <h2>Access Denied</h2>
            <p>
            You do not have permission to access
            this page.
            </p>
        </div>
        """,
        "Access Denied"
    ), 403


@app.errorhandler(404)
def not_found(error):

    return page(
        """
        <div class="card">
            <h2>Page Not Found</h2>
            <p>
            The requested resource does not exist.
            </p>
        </div>
        """,
        "Not Found"
    ), 404


@app.errorhandler(413)
def too_large(error):

    return page(
        """
        <div class="card">
            <h2>File Too Large</h2>
            <p>
            Maximum upload size is 10 MB.
            </p>
        </div>
        """,
        "File Too Large"
    ), 413


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

    host = os.getenv(
        "HOST",
        "0.0.0.0"
    )

    print("=" * 60)
    print("KOJA AFRICA")
    print("Knowledge • Questions • Answers")
    print("=" * 60)
    print(f"Running on port {port}")

    app.run(
        host=host,
        port=port,
        debug=False
    )

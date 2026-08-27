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
    ""
)

if not SECRET_KEY:
    SECRET_KEY = secrets.token_hex(32)

APP_NAME = "KOJA AFRICA"

APP_TAGLINE = (
    "Assignment Questions • Academic Answers • Learning Resources"
)

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
# ALLOWED FILE TYPES
# ============================================================

ALLOWED_DOCUMENT_EXTENSIONS = {
    "pdf",
    "doc",
    "docx",
    "ppt",
    "pptx",
    "xls",
    "xlsx",
    "txt",
    "csv",
    "jpg",
    "jpeg",
    "png",
}


# ============================================================
# FLASK
# ============================================================

app = Flask(__name__)

app.secret_key = SECRET_KEY

app.config["MAX_CONTENT_LENGTH"] = MAX_FILE_SIZE

app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

# Render uses HTTPS.
if os.getenv("FLASK_ENV") == "production":
    app.config["SESSION_COOKIE_SECURE"] = True


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)


# ============================================================
# GENERAL HELPERS
# ============================================================

def utc_now():
    return datetime.now(
        timezone.utc
    ).isoformat()


def valid_uuid(value):
    try:
        uuid.UUID(str(value))
        return True
    except Exception:
        return False


def clean_filename(filename):
    """
    Prevent dangerous paths and normalize filenames.
    """

    if not filename:
        return "document"

    filename = os.path.basename(filename)

    filename = filename.replace(
        "\\",
        "_"
    )

    filename = filename.replace(
        "/",
        "_"
    )

    filename = filename.replace(
        "\x00",
        ""
    )

    filename = filename.strip()

    if not filename:
        filename = "document"

    return filename


def file_extension(filename):
    filename = clean_filename(filename)

    if "." not in filename:
        return ""

    return filename.rsplit(
        ".",
        1
    )[1].lower()


# ============================================================
# SUPABASE HEADERS
# ============================================================

def supabase_headers(use_service=True):

    if use_service:
        key = SUPABASE_SERVICE_KEY
    else:
        key = SUPABASE_ANON_KEY

    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }


# ============================================================
# SUPABASE REST REQUEST
# ============================================================

def supabase_request(
    method,
    table,
    params=None,
    json_data=None,
    use_service=True,
    headers_extra=None
):

    if not SUPABASE_URL:
        logging.error(
            "SUPABASE_URL is missing."
        )
        return None

    if not SUPABASE_SERVICE_KEY and use_service:
        logging.error(
            "SUPABASE_SERVICE_KEY is missing."
        )
        return None

    url = (
        f"{SUPABASE_URL}"
        f"/rest/v1/{table}"
    )

    headers = supabase_headers(
        use_service
    )

    if headers_extra:
        headers.update(
            headers_extra
        )

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
                "Supabase %s %s failed: %s",
                method,
                table,
                response.text
            )

        return response

    except requests.RequestException as exc:

        logging.error(
            "Supabase connection error: %s",
            exc
        )

        return None


# ============================================================
# SUPABASE RPC
# ============================================================

def supabase_rpc(
    function_name,
    payload=None
):

    url = (
        f"{SUPABASE_URL}"
        f"/rest/v1/rpc/{function_name}"
    )

    try:

        response = requests.post(
            url,
            headers=supabase_headers(True),
            json=payload or {},
            timeout=25
        )

        if not response.ok:

            logging.error(
                "RPC %s failed: %s",
                function_name,
                response.text
            )

        return response

    except requests.RequestException as exc:

        logging.error(
            "RPC connection error: %s",
            exc
        )

        return None


# ============================================================
# DATABASE SELECT
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
        params.update(
            filters
        )

    if order:
        params["order"] = order

    if limit:
        params["limit"] = str(
            limit
        )

    response = supabase_request(
        "GET",
        table,
        params=params
    )

    if not response:
        return []

    if not response.ok:
        return []

    try:

        data = response.json()

        if isinstance(data, list):
            return data

        return []

    except Exception:

        return []


# ============================================================
# DATABASE INSERT
# ============================================================

def db_insert(
    table,
    data,
    returning=True
):

    if returning:

        headers_extra = {
            "Prefer":
                "return=representation"
        }

    else:

        headers_extra = {
            "Prefer":
                "return=minimal"
        }

    response = supabase_request(
        "POST",
        table,
        json_data=data,
        headers_extra=headers_extra
    )

    if not response:
        return []

    if not response.ok:
        return []

    if not returning:
        return [{"success": True}]

    try:

        result = response.json()

        if isinstance(result, list):
            return result

        return []

    except Exception:

        return []


# ============================================================
# DATABASE UPDATE
# ============================================================

def db_update(
    table,
    filters,
    data,
    returning=True
):

    if returning:

        headers_extra = {
            "Prefer":
                "return=representation"
        }

    else:

        headers_extra = {
            "Prefer":
                "return=minimal"
        }

    response = supabase_request(
        "PATCH",
        table,
        params=filters,
        json_data=data,
        headers_extra=headers_extra
    )

    if not response:
        return []

    if not response.ok:
        return []

    if not returning:
        return [{"success": True}]

    try:

        result = response.json()

        if isinstance(result, list):
            return result

        return []

    except Exception:

        return []


# ============================================================
# DATABASE DELETE
# ============================================================

def db_delete(
    table,
    filters
):

    response = supabase_request(
        "DELETE",
        table,
        params=filters,
        headers_extra={
            "Prefer":
                "return=minimal"
        }
    )

    return bool(
        response
        and response.ok
    )


# ============================================================
# PASSWORD SECURITY
# ============================================================

PBKDF2_ITERATIONS = 210000


def hash_password(password):

    salt = secrets.token_bytes(
        16
    )

    password_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS
    )

    return (
        salt.hex()
        + "$"
        + password_hash.hex()
    )


def verify_password(
    password,
    stored
):

    try:

        salt_hex, hash_hex = (
            stored.split(
                "$",
                1
            )
        )

        salt = bytes.fromhex(
            salt_hex
        )

        calculated = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            PBKDF2_ITERATIONS
        )

        return secrets.compare_digest(
            calculated.hex(),
            hash_hex
        )

    except Exception:

        return False


# ============================================================
# CURRENT USER
# ============================================================

def current_user():

    user_id = session.get(
        "user_id"
    )

    if not user_id:
        return None

    users = db_select(
        "profiles",
        filters={
            "id":
                f"eq.{user_id}"
        },
        limit=1
    )

    if not users:
        return None

    return users[0]


# ============================================================
# LOGIN REQUIRED
# ============================================================

def login_required(view):

    @wraps(view)
    def wrapped(
        *args,
        **kwargs
    ):

        if not session.get(
            "user_id"
        ):

            flash(
                "Please log in first."
            )

            return redirect(
                url_for("login")
            )

        return view(
            *args,
            **kwargs
        )

    return wrapped


# ============================================================
# ADMIN REQUIRED
# ============================================================

def admin_required(view):

    @wraps(view)
    def wrapped(
        *args,
        **kwargs
    ):

        user = current_user()

        if not user:

            session.clear()

            return redirect(
                url_for("login")
            )

        if user.get("role") != "admin":

            abort(403)

        return view(
            *args,
            **kwargs
        )

    return wrapped


# ============================================================
# ACTIVITY LOG
# ============================================================

def log_activity(
    action,
    description=""
):

    user_id = session.get(
        "user_id"
    )

    if not user_id:
        return

    if not valid_uuid(user_id):
        return

    data = {
        "id":
            str(uuid.uuid4()),

        "user_id":
            user_id,

        "action":
            action,

        "description":
            description,

        "created_at":
            utc_now()
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
# STORAGE BUCKET
# ============================================================

def ensure_storage_bucket():

    if (
        not SUPABASE_URL
        or
        "YOUR-PROJECT"
        in SUPABASE_URL
    ):

        logging.warning(
            "SUPABASE_URL has not been configured."
        )

        return False

    if not SUPABASE_SERVICE_KEY:

        logging.warning(
            "SUPABASE_SERVICE_KEY has not been configured."
        )

        return False

    bucket_url = (
        f"{SUPABASE_URL}"
        f"/storage/v1/bucket/"
        f"{STORAGE_BUCKET}"
    )

    headers = supabase_headers(
        True
    )

    try:

        check = requests.get(
            bucket_url,
            headers=headers,
            timeout=20
        )

        if check.ok:

            logging.info(
                "Storage bucket '%s' is ready.",
                STORAGE_BUCKET
            )

            return True

        if check.status_code != 404:

            logging.error(
                "Storage bucket check failed: %s",
                check.text
            )

            return False

        create_url = (
            f"{SUPABASE_URL}"
            f"/storage/v1/bucket"
        )

        response = requests.post(
            create_url,
            headers=headers,
            json={
                "id":
                    STORAGE_BUCKET,

                "name":
                    STORAGE_BUCKET,

                "public":
                    False,

                "file_size_limit":
                    MAX_FILE_SIZE
            },
            timeout=20
        )

        if response.ok:

            logging.info(
                "Created storage bucket '%s'.",
                STORAGE_BUCKET
            )

            return True

        if response.status_code == 409:

            return True

        logging.error(
            "Could not create storage bucket: %s",
            response.text
        )

        return False

    except requests.RequestException as exc:

        logging.error(
            "Storage bucket connection error: %s",
            exc
        )

        return False


# ============================================================
# STORAGE UPLOAD
# ============================================================

def upload_storage(
    file_bytes,
    filename,
    content_type
):

    if not file_bytes:

        logging.error(
            "Cannot upload empty file."
        )

        return None

    if len(file_bytes) > MAX_FILE_SIZE:

        logging.error(
            "File exceeds maximum size."
        )

        return None

    safe_name = clean_filename(
        filename
    )

    extension = file_extension(
        safe_name
    )

    if (
        extension
        not in ALLOWED_DOCUMENT_EXTENSIONS
    ):

        logging.error(
            "File extension not allowed: %s",
            extension
        )

        return None

    # Unique storage directory.
    path = (
        "documents/"
        + str(uuid.uuid4())
        + "/"
        + safe_name
    )

    url = (
        f"{SUPABASE_URL}"
        f"/storage/v1/object/"
        f"{STORAGE_BUCKET}/"
        f"{path}"
    )

    headers = supabase_headers(
        True
    )

    headers["Content-Type"] = (
        content_type
        or
        "application/octet-stream"
    )

    headers["x-upsert"] = "false"

    try:

        response = requests.post(
            url,
            headers=headers,
            data=file_bytes,
            timeout=60
        )

        if not response.ok:

            logging.error(
                "Storage upload failed: "
                "%s %s",
                response.status_code,
                response.text
            )

            return None

        logging.info(
            "Document uploaded: %s",
            path
        )

        return path

    except requests.RequestException as exc:

        logging.error(
            "Storage upload connection error: %s",
            exc
        )

        return None


# ============================================================
# STORAGE DOWNLOAD
# ============================================================

def download_storage(path):

    if not path:
        return None

    if ".." in path:

        logging.warning(
            "Invalid storage path."
        )

        return None

    if path.startswith("/"):

        logging.warning(
            "Invalid storage path."
        )

        return None

    url = (
        f"{SUPABASE_URL}"
        f"/storage/v1/object/"
        f"{STORAGE_BUCKET}/"
        f"{path}"
    )

    try:

        response = requests.get(
            url,
            headers=supabase_headers(True),
            timeout=60
        )

        if not response.ok:

            logging.error(
                "Storage download failed: "
                "%s %s",
                response.status_code,
                response.text
            )

            return None

        return response.content

    except requests.RequestException as exc:

        logging.error(
            "Storage download error: %s",
            exc
        )

        return None


# ============================================================
# PDF GENERATION
# ============================================================

def create_pdf(
    title,
    body,
    metadata=None
):

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

    title_style.alignment = (
        TA_CENTER
    )

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
                    escape(
                        str(key)
                    ),
                    styles["BodyText"]
                ),

                Paragraph(
                    escape(
                        str(value)
                    ),
                    styles["BodyText"]
                )
            ])

        table = Table(
            rows,
            colWidths=[
                120,
                350
            ]
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

        story.append(
            table
        )

        story.append(
            Spacer(1, 15)
        )

    for paragraph in body.split(
        "\n"
    ):

        if paragraph.strip():

            story.append(
                Paragraph(
                    escape(
                        paragraph
                    ),
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

    document.build(
        story
    )

    buffer.seek(0)

    return buffer


# ============================================================
# BASE HTML
# ============================================================

BASE_HTML = """
<!doctype html>

<html>

<head>

<meta name="viewport"
content="width=device-width, initial-scale=1">

<meta name="description"
content="KOJA AFRICA - Academic Questions, Answers and Learning Resources">

<title>
{{ title or "KOJA AFRICA" }}
</title>

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

    padding:
        15px 5%;

    display: flex;

    justify-content:
        space-between;

    align-items:
        center;

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

    padding:
        9px 12px;

    border-radius: 8px;

}

.navlinks a:hover {

    background:
        rgba(255,255,255,.12);

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

    padding:
        45px 30px;

    margin-bottom: 25px;

}

.hero h1 {

    font-size: 38px;

    margin:
        0 0 12px;

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
        repeat(
            auto-fit,
            minmax(230px,1fr)
        );

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

    border:
        1px solid #d6dce8;

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

    padding:
        11px 16px;

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

    padding:
        5px 9px;

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

    border-left:
        4px solid #0b397f;

    padding-left: 15px;

}

.small {

    color: #687386;

    font-size: 13px;

}

.file-card {

    border:
        1px solid #e2e7f0;

    border-radius: 12px;

    padding: 16px;

    margin-top: 12px;

}

.danger {

    color: #b3261e;

}

.success {

    color: #168653;

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

        align-items:
            flex-start;

    }

    .navlinks {

        width: 100%;

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

<a href="{{ url_for('home') }}">
Home
</a>

{% if session.get("user_id") %}

<a href="{{ url_for('dashboard') }}">
Dashboard
</a>

<a href="{{ url_for('documents') }}">
Documents
</a>

{% if session.get("role") == "admin" %}

<a href="{{ url_for('admin_dashboard') }}">
Admin
</a>

{% endif %}

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

KOJA AFRICA © 2026

<br>

Knowledge • Questions • Answers

</footer>

</body>

</html>
"""


# ============================================================
# PAGE RENDERER
# ============================================================

def page(
    content,
    title="KOJA AFRICA"
):

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

<h1>
Learn. Ask. Discover.
</h1>

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

<h3>
Ask Questions
</h3>

<p>
Submit academic questions and receive
structured answers.
</p>

</div>

<div class="card">

<h3>
Academic Answers
</h3>

<p>
Receive answers to your submitted
academic questions.
</p>

</div>

<div class="card">

<h3>
Learning Resources
</h3>

<p>
Access a growing library of academic
documents and resources.
</p>

</div>

<div class="card">

<h3>
Digital Documents
</h3>

<p>
Documents are stored securely and can
be downloaded by authorized users.
</p>

</div>

<div class="card">

<h3>
Future Marketplace
</h3>

<p>
KOJA is designed to support free and
premium educational resources.
</p>

</div>

</div>

"""

    return page(
        content
    )


# ============================================================
# REGISTER
# ============================================================

@app.route(
    "/register",
    methods=[
        "GET",
        "POST"
    ]
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

        if (
            not name
            or
            not email
            or
            not password
        ):

            flash(
                "Complete all fields."
            )

            return redirect(
                url_for("register")
            )

        if len(password) < 8:

            flash(
                "Password must contain at least 8 characters."
            )

            return redirect(
                url_for("register")
            )

        existing = db_select(
            "profiles",
            filters={
                "email":
                    f"eq.{email}"
            },
            limit=1
        )

        if existing:

            flash(
                "An account with that email already exists."
            )

            return redirect(
                url_for("login")
            )

        user_id = str(
            uuid.uuid4()
        )

        user_data = {

            "id":
                user_id,

            "name":
                name,

            "email":
                email,

            "password_hash":
                hash_password(
                    password
                ),

            "role":
                "student",

            "created_at":
                utc_now()
        }

        result = db_insert(
            "profiles",
            user_data
        )

        if not result:

            flash(
                "Registration failed. Check your Supabase profiles table."
            )

            return redirect(
                url_for("register")
            )

        session.clear()

        session["user_id"] = (
            user_id
        )

        session["role"] = (
            "student"
        )

        log_activity(
            "registration",
            "New student account created."
        )

        flash(
            "Account created successfully."
        )

        return redirect(
            url_for("dashboard")
        )

    content = """

<div class="card">

<h2>
Create Student Account
</h2>

<form method="POST">

<label>
Full name
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
minlength="8"
required
>

<button type="submit">
Create Account
</button>

</form>

</div>

"""

    return page(
        content,
        "Create Account"
    )


# ============================================================
# LOGIN
# ============================================================

@app.route(
    "/login",
    methods=[
        "GET",
        "POST"
    ]
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

        users = db_select(
            "profiles",
            filters={
                "email":
                    f"eq.{email}"
            },
            limit=1
        )

        if not users:

            flash(
                "Invalid email or password."
            )

            return redirect(
                url_for("login")
            )

        user = users[0]

        if not verify_password(
            password,
            user.get(
                "password_hash",
                ""
            )
        ):

            flash(
                "Invalid email or password."
            )

            return redirect(
                url_for("login")
            )

        session.clear()

        session["user_id"] = (
            user["id"]
        )

        session["role"] = (
            user.get(
                "role",
                "student"
            )
        )

        log_activity(
            "login",
            "User logged in."
        )

        if user.get(
            "role"
        ) == "admin":

            return redirect(
                url_for(
                    "admin_dashboard"
                )
            )

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

<button type="submit">
Login
</button>

</form>

</div>

"""

    return page(
        content,
        "Login"
    )


# ============================================================
# LOGOUT
# ============================================================

@app.route("/logout")
def logout():

    if session.get(
        "user_id"
    ):

        log_activity(
            "logout",
            "User logged out."
        )

    session.clear()

    flash(
        "You have been logged out."
    )

    return redirect(
        url_for("home")
    )


# ============================================================
# STUDENT DASHBOARD
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

    if user.get(
        "role"
    ) == "admin":

        return redirect(
            url_for(
                "admin_dashboard"
            )
        )

    questions_rows = db_select(
        "questions",
        filters={
            "student_id":
                f"eq.{user['id']}"
        },
        order="created_at.desc",
        limit=10
    )

    # Student gets general documents
    # plus documents specifically assigned.
    general_documents = db_select(
        "documents",
        filters={
            "recipient_id":
                "is.null"
        },
        order="created_at.desc",
        limit=100
    )

    private_documents = db_select(
        "documents",
        filters={
            "recipient_id":
                f"eq.{user['id']}"
        },
        order="created_at.desc",
        limit=100
    )

    documents_rows = (
        general_documents
        + private_documents
    )

    # Remove duplicates.
    unique_documents = {}

    for document in documents_rows:

        document_id = document.get(
            "id"
        )

        if document_id:

            unique_documents[
                document_id
            ] = document

    documents_rows = list(
        unique_documents.values()
    )

    documents_rows.sort(
        key=lambda x:
            str(
                x.get(
                    "created_at",
                    ""
                )
            ),
        reverse=True
    )

    unread = sum(
        1
        for document
        in documents_rows
        if not document.get(
            "is_read",
            False
        )
    )

    content = f"""

<section class="hero">

<h1>
Welcome,
{escape(
    user.get(
        "name",
        "Student"
    )
)}
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
{len(questions_rows)}
</div>

<div>
My Questions
</div>

</div>

<div class="card">

<div class="stat">
{len(documents_rows)}
</div>

<div>
Available Documents
</div>

</div>

<div class="card">

<div class="stat">
{unread}
</div>

<div>
Unread Documents
</div>

</div>

</div>

<div class="card">

<h2>
My Questions
</h2>

"""

    if questions_rows:

        for question in questions_rows:

            answer = (
                question.get(
                    "answer"
                )
                or
                ""
            )

            content += f"""

<div class="question">

<h3>
{escape(
    question.get(
        "subject",
        "Question"
    )
)}
</h3>

<p>
{escape(
    question.get(
        "question",
        ""
    )
)}
</p>

<span class="badge">
{escape(
    question.get(
        "status",
        "pending"
    )
)}
</span>

"""

            if answer:

                content += f"""

<p>
<strong>
Answer:
</strong>
<br>
{escape(answer)}
</p>

<a
class="btn btn-light"
href="/questions/{question.get('id')}/pdf">
Download PDF
</a>

"""

            content += """
</div>

<hr>

"""

    else:

        content += """

<p>
You have not submitted any questions yet.
</p>

"""

    content += """
</div>
"""

    return page(
        content,
        "Student Dashboard"
    )


# ============================================================
# NEW QUESTION
# ============================================================

@app.route(
    "/questions/new",
    methods=[
        "GET",
        "POST"
    ]
)
@login_required
def new_question():

    user = current_user()

    if user and user.get(
        "role"
    ) == "admin":

        return redirect(
            url_for(
                "admin_questions"
            )
        )

    if request.method == "POST":

        subject = request.form.get(
            "subject",
            ""
        ).strip()

        question = request.form.get(
            "question",
            ""
        ).strip()

        if (
            not subject
            or
            not question
        ):

            flash(
                "Enter the subject and question."
            )

            return redirect(
                url_for(
                    "new_question"
                )
            )

        data = {

            "id":
                str(uuid.uuid4()),

            "student_id":
                session["user_id"],

            "subject":
                subject,

            "question":
                question,

            "status":
                "pending",

            "created_at":
                utc_now()
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

            flash(
                "Question submitted successfully."
            )

            return redirect(
                url_for(
                    "dashboard"
                )
            )

        flash(
            "Unable to submit question."
        )

    content = """

<div class="card">

<h2>
Ask KOJA
</h2>

<form method="POST">

<label>
Subject
</label>

<input
name="subject"
placeholder="e.g. Chemistry"
required
>

<label>
Question
</label>

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

    return page(
        content,
        "Ask Question"
    )


# ============================================================
# STUDENT QUESTIONS
# ============================================================

@app.route("/questions")
@login_required
def questions():

    user = current_user()

    if user and user.get(
        "role"
    ) == "admin":

        return redirect(
            url_for(
                "admin_questions"
            )
        )

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

<h2>
My Questions
</h2>

<a class="btn"
href="/questions/new">
New Question
</a>

</div>

"""

    for question in rows:

        answer = (
            question.get(
                "answer"
            )
            or
            ""
        )

        content += f"""

<div class="card">

<h3>
{escape(
    question.get(
        "subject",
        ""
    )
)}
</h3>

<p>
{escape(
    question.get(
        "question",
        ""
    )
)}
</p>

<span class="badge">
{escape(
    question.get(
        "status",
        "pending"
    )
)}
</span>

<h4>
Answer
</h4>

<p>
{
    escape(answer)
    if answer
    else
    "Awaiting academic answer."
}
</p>

"""

        if answer:

            content += f"""

<a
class="btn btn-light"
href="/questions/{question.get('id')}/pdf">
Download PDF
</a>

"""

        content += """
</div>
"""

    return page(
        content,
        "My Questions"
    )


# ============================================================
# DOCUMENT LIBRARY
# ============================================================

@app.route("/documents")
@login_required
def documents():

    user = current_user()

    if not user:

        session.clear()

        return redirect(
            url_for("login")
        )

    is_admin = (
        user.get("role")
        ==
        "admin"
    )

    search = request.args.get(
        "q",
        ""
    ).strip().lower()

    if is_admin:

        rows = db_select(
            "documents",
            order="created_at.desc",
            limit=500
        )

    else:

        # General Library
        general_rows = db_select(
            "documents",
            filters={
                "recipient_id":
                    "is.null"
            },
            order="created_at.desc",
            limit=500
        )

        # Documents assigned to this student
        private_rows = db_select(
            "documents",
            filters={
                "recipient_id":
                    f"eq.{user['id']}"
            },
            order="created_at.desc",
            limit=500
        )

        combined = (
            general_rows
            +
            private_rows
        )

        unique = {}

        for row in combined:

            row_id = row.get(
                "id"
            )

            if row_id:

                unique[
                    row_id
                ] = row

        rows = list(
            unique.values()
        )

        rows.sort(
            key=lambda x:
                str(
                    x.get(
                        "created_at",
                        ""
                    )
                ),
            reverse=True
        )

    if search:

        rows = [
            row
            for row in rows
            if search in (
                str(
                    row.get(
                        "title",
                        ""
                    )
                )
                +
                " "
                +
                str(
                    row.get(
                        "description",
                        ""
                    )
                )
                +
                " "
                +
                str(
                    row.get(
                        "filename",
                        ""
                    )
                )
            ).lower()
        ]

    search_value = escape(
        request.args.get(
            "q",
            ""
        )
    )

    content = f"""

<div class="card">

<h2>
KOJA AFRICA Document Library
</h2>

<p>
Access academic documents securely stored
by KOJA AFRICA.
</p>

<form method="GET">

<input
name="q"
value="{search_value}"
placeholder="Search documents..."
>

<button type="submit">
Search
</button>

</form>

"""

    if is_admin:

        content += """

<p class="small">
Administrator view: all documents are visible.
</p>

"""

    else:

        content += """

<p class="small">
You can access general library documents and
documents specifically assigned to your account.
</p>

"""

    content += """
</div>
"""

    if not rows:

        content += """

<div class="card">

<h3>
No documents found
</h3>

<p>
There are currently no documents available.
</p>

</div>

"""

        return page(
            content,
            "Documents"
        )

    for document in rows:

        price = (
            document.get(
                "price",
                0
            )
            or
            0
        )

        try:

            price = float(
                price
            )

        except Exception:

            price = 0

        is_paid = (
            price > 0
        )

        recipient_id = (
            document.get(
                "recipient_id"
            )
        )

        if recipient_id:

            access_label = (
                "Assigned document"
            )

        else:

            access_label = (
                "General Library"
            )

        if is_paid:

            badge = """
<span class="badge badge-paid">
PAID
</span>
"""

        else:

            badge = """
<span class="badge badge-free">
FREE
</span>
"""

        content += f"""

<div class="card">

<h3>
{escape(
    document.get(
        "title",
        "Document"
    )
)}
</h3>

{badge}

<p>
{escape(
    document.get(
        "description",
        ""
    )
)}
</p>

<p class="small">

<strong>
File:
</strong>

{escape(
    document.get(
        "filename",
        "Document"
    )
)}

<br>

<strong>
Access:
</strong>

{escape(
    access_label
)}

<br>

<strong>
Price:
</strong>

K{price:.2f}

</p>

<a
class="btn"
href="/documents/{document.get('id')}">
Open Document
</a>

</div>

"""

    return page(
        content,
        "Documents"
    )


# ============================================================
# DOCUMENT VIEW
# ============================================================

@app.route(
    "/documents/<document_id>"
)
@login_required
def document_view(
    document_id
):

    if not valid_uuid(
        document_id
    ):

        abort(404)

    rows = db_select(
        "documents",
        filters={
            "id":
                f"eq.{document_id}"
        },
        limit=1
    )

    if not rows:

        abort(404)

    document = rows[0]

    user = current_user()

    if not user:

        abort(403)

    is_admin = (
        user.get("role")
        ==
        "admin"
    )

    if not is_admin:

        recipient_id = (
            document.get(
                "recipient_id"
            )
        )

        # NULL recipient = General Library
        # Specific recipient = private document.
        if (
            recipient_id
            and
            recipient_id
            !=
            session["user_id"]
        ):

            abort(403)

    price = (
        document.get(
            "price",
            0
        )
        or
        0
    )

    try:

        price = float(
            price
        )

    except Exception:

        price = 0

    is_paid = (
        price > 0
    )

    content = f"""

<div class="card">

<h2>
{escape(
    document.get(
        "title",
        "Document"
    )
)}
</h2>

<p>
{escape(
    document.get(
        "description",
        ""
    )
)}
</p>

<div class="file-card">

<p>

<strong>
File:
</strong>

{escape(
    document.get(
        "filename",
        "Document"
    )
)}

</p>

<p>

<strong>
Price:
</strong>

K{price:.2f}

</p>

<p>

<strong>
Status:
</strong>

<span class="badge">

{escape(
    str(
        document.get(
            "status",
            "available"
        )
    )
)}

</span>

</p>

"""

    if document.get(
        "recipient_id"
    ):

        content += """

<p class="small">
This document was specifically assigned
to a student.
</p>

"""

    else:

        content += """

<p class="small">
This document is available through the
KOJA AFRICA General Library.
</p>

"""

    content += """
</div>
"""

    if is_admin:

        content += f"""

<div style="margin-top:20px">

<a
class="btn"
href="/documents/{document_id}/download">
Download Document
</a>

</div>

"""

    else:

        content += f"""

<div style="margin-top:20px">

<a
class="btn btn-green"
href="/documents/{document_id}/received">
Mark as Received
</a>

<a
class="btn"
href="/documents/{document_id}/read">
Mark as Read
</a>

"""

        if is_paid:

            content += """

<p class="flash">

This is a paid document.

Download will become available after
a completed purchase is recorded.

</p>

"""

        else:

            content += f"""

<a
class="btn btn-light"
href="/documents/{document_id}/download">
Download
</a>

"""

        content += """
</div>
"""

    content += """
</div>
"""

    return page(
        content,
        "Document"
    )


# ============================================================
# MARK DOCUMENT RECEIVED
# ============================================================

@app.route(
    "/documents/<document_id>/received"
)
@login_required
def mark_received(
    document_id
):

    if not valid_uuid(
        document_id
    ):

        abort(404)

    document_rows = db_select(
        "documents",
        filters={
            "id":
                f"eq.{document_id}"
        },
        limit=1
    )

    if not document_rows:

        abort(404)

    document = document_rows[0]

    user = current_user()

    if not user:

        abort(403)

    if user.get(
        "role"
    ) != "admin":

        recipient_id = (
            document.get(
                "recipient_id"
            )
        )

        if (
            recipient_id
            and
            recipient_id
            !=
            session["user_id"]
        ):

            abort(403)

    response = supabase_rpc(
        "mark_document_received",
        {
            "document_uuid":
                document_id
        }
    )

    if response and response.ok:

        log_activity(
            "document_received",
            document_id
        )

        flash(
            "Document marked as received."
        )

    else:

        # Fallback direct update.
        result = db_update(
            "documents",
            {
                "id":
                    f"eq.{document_id}"
            },
            {
                "status":
                    "received"
            }
        )

        if result:

            log_activity(
                "document_received",
                document_id
            )

            flash(
                "Document marked as received."
            )

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
# MARK DOCUMENT READ
# ============================================================

@app.route(
    "/documents/<document_id>/read"
)
@login_required
def mark_read(
    document_id
):

    if not valid_uuid(
        document_id
    ):

        abort(404)

    document_rows = db_select(
        "documents",
        filters={
            "id":
                f"eq.{document_id}"
        },
        limit=1
    )

    if not document_rows:

        abort(404)

    document = document_rows[0]

    user = current_user()

    if not user:

        abort(403)

    if user.get(
        "role"
    ) != "admin":

        recipient_id = (
            document.get(
                "recipient_id"
            )
        )

        if (
            recipient_id
            and
            recipient_id
            !=
            session["user_id"]
        ):

            abort(403)

    response = supabase_rpc(
        "mark_document_read",
        {
            "document_uuid":
                document_id
        }
    )

    if response and response.ok:

        log_activity(
            "document_read",
            document_id
        )

        flash(
            "Document marked as read."
        )

    else:

        result = db_update(
            "documents",
            {
                "id":
                    f"eq.{document_id}"
            },
            {
                "is_read":
                    True
            }
        )

        if result:

            log_activity(
                "document_read",
                document_id
            )

            flash(
                "Document marked as read."
            )

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
# SECURE DOCUMENT DOWNLOAD
# ============================================================

@app.route(
    "/documents/<document_id>/download"
)
@login_required
def download_document(
    document_id
):

    if not valid_uuid(
        document_id
    ):

        abort(404)

    rows = db_select(
        "documents",
        filters={
            "id":
                f"eq.{document_id}"
        },
        limit=1
    )

    if not rows:

        abort(404)

    document = rows[0]

    user = current_user()

    if not user:

        abort(403)

    is_admin = (
        user.get("role")
        ==
        "admin"
    )

    # ========================================================
    # ACCESS CONTROL
    # ========================================================

    if not is_admin:

        recipient_id = (
            document.get(
                "recipient_id"
            )
        )

        # General document:
        # recipient_id = NULL
        #
        # Private document:
        # recipient_id = student ID
        #
        # Another student's private document:
        # DENY

        if (
            recipient_id
            and
            recipient_id
            !=
            session["user_id"]
        ):

            abort(403)

    # ========================================================
    # PAYMENT CONTROL
    # ========================================================

    price = (
        document.get(
            "price",
            0
        )
        or
        0
    )

    try:

        price = float(
            price
        )

    except Exception:

        price = 0

    if (
        price > 0
        and
        not is_admin
    ):

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
                "Payment is required before downloading this document."
            )

            return redirect(
                url_for(
                    "document_view",
                    document_id=document_id
                )
            )

    # ========================================================
    # STORAGE PATH
    # ========================================================

    storage_path = (
        document.get(
            "storage_path"
        )
    )

    if not storage_path:

        flash(
            "This document has no storage file."
        )

        return redirect(
            url_for(
                "document_view",
                document_id=document_id
            )
        )

    # ========================================================
    # RETRIEVE FILE
    # ========================================================

    file_bytes = download_storage(
        storage_path
    )

    if not file_bytes:

        flash(
            "The document could not be retrieved from storage."
        )

        return redirect(
            url_for(
                "document_view",
                document_id=document_id
            )
        )

    # ========================================================
    # DOWNLOAD LOG
    # ========================================================

    db_insert(
        "document_downloads",
        {
            "id":
                str(uuid.uuid4()),

            "document_id":
                document_id,

            "user_id":
                session["user_id"],

            "created_at":
                utc_now()
        },
        returning=False
    )

    log_activity(
        "document_download",
        document.get(
            "title",
            ""
        )
    )

    filename = (
        document.get(
            "filename"
        )
        or
        "koja-document"
    )

    filename = clean_filename(
        filename
    )

    mime_type = (
        document.get(
            "mime_type"
        )
        or
        "application/octet-stream"
    )

    return send_file(
        io.BytesIO(
            file_bytes
        ),
        as_attachment=True,
        download_name=filename,
        mimetype=mime_type
    )


# ============================================================
# ADMIN DASHBOARD
# ============================================================

@app.route("/admin")
@admin_required
def admin_dashboard():

    users = db_select(
        "profiles",
        select=(
            "id,name,email,role,created_at"
        ),
        order="created_at.desc",
        limit=500
    )

    questions_rows = db_select(
        "questions",
        order="created_at.desc",
        limit=500
    )

    documents_rows = db_select(
        "documents",
        order="created_at.desc",
        limit=500
    )

    purchases = db_select(
        "purchases",
        order="created_at.desc",
        limit=500
    )

    content = f"""

<section class="hero">

<h1>
Admin Control Centre
</h1>

<p>
KOJA AFRICA administration, academic
content and digital document management.
</p>

</section>

<div class="grid">

<div class="card">

<div class="stat">
{len(users)}
</div>

Users

</div>

<div class="card">

<div class="stat">
{len(questions_rows)}
</div>

Questions

</div>

<div class="card">

<div class="stat">
{len(documents_rows)}
</div>

Documents

</div>

<div class="card">

<div class="stat">
{len(purchases)}
</div>

Purchases

</div>

</div>

<div class="grid">

<div class="card">

<h3>
Academic Management
</h3>

<a class="btn"
href="/admin/questions">
Questions
</a>

</div>

<div class="card">

<h3>
Document Management
</h3>

<a class="btn"
href="/admin/documents">
Documents
</a>

</div>

<div class="card">

<h3>
Users
</h3>

<a class="btn"
href="/admin/users">
Manage Users
</a>

</div>

<div class="card">

<h3>
Activity
</h3>

<a class="btn"
href="/admin/logs">
View Logs
</a>

</div>

</div>

"""

    return page(
        content,
        "Admin"
    )


# ============================================================
# ADMIN QUESTIONS
# ============================================================

@app.route("/admin/questions")
@admin_required
def admin_questions():

    rows = db_select(
        "questions",
        order="created_at.desc",
        limit=500
    )

    content = """

<div class="card">

<h2>
Student Questions
</h2>

</div>

"""

    if not rows:

        content += """

<div class="card">

<p>
No questions have been submitted.
</p>

</div>

"""

    for question in rows:

        content += f"""

<div class="card">

<h3>
{escape(
    question.get(
        "subject",
        ""
    )
)}
</h3>

<p>
{escape(
    question.get(
        "question",
        ""
    )
)}
</p>

<span class="badge">
{escape(
    question.get(
        "status",
        "pending"
    )
)}
</span>

<br><br>

<a class="btn"
href="/admin/questions/{question.get('id')}">
Open & Answer
</a>

</div>

"""

    return page(
        content,
        "Admin Questions"
    )


# ============================================================
# ADMIN ANSWER
# ============================================================

@app.route(
    "/admin/questions/<question_id>",
    methods=[
        "GET",
        "POST"
    ]
)
@admin_required
def admin_question(
    question_id
):

    if not valid_uuid(
        question_id
    ):

        abort(404)

    rows = db_select(
        "questions",
        filters={
            "id":
                f"eq.{question_id}"
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
            else
            "pending"
        )

        result = db_update(
            "questions",
            {
                "id":
                    f"eq.{question_id}"
            },
            {
                "answer":
                    answer,

                "status":
                    status,

                "answered_by":
                    session["user_id"],

                "answered_at":
                    utc_now()
            }
        )

        if result:

            log_activity(
                "question_answered",
                question_id
            )

            student_id = (
                question.get(
                    "student_id"
                )
            )

            if valid_uuid(
                student_id
            ):

                db_insert(
                    "notifications",
                    {
                        "id":
                            str(
                                uuid.uuid4()
                            ),

                        "user_id":
                            student_id,

                        "title":
                            "Your question has been answered",

                        "message":
                            question.get(
                                "subject",
                                ""
                            ),

                        "is_read":
                            False,

                        "created_at":
                            utc_now()
                    },
                    returning=False
                )

            flash(
                "Answer saved."
            )

            return redirect(
                url_for(
                    "admin_questions"
                )
            )

        flash(
            "Unable to save answer."
        )

    content = f"""

<div class="card">

<h2>
{escape(
    question.get(
        "subject",
        ""
    )
)}
</h2>

<p>
<strong>
Student Question:
</strong>
</p>

<p>
{escape(
    question.get(
        "question",
        ""
    )
)}
</p>

<form method="POST">

<label>
Academic Answer
</label>

<textarea
name="answer"
required
>{escape(
    question.get(
        "answer"
    )
    or
    ""
)}</textarea>

<button>
Save Answer
</button>

</form>

</div>

"""

    return page(
        content,
        "Answer Question"
    )


# ============================================================
# ADMIN DOCUMENT MANAGEMENT
# ============================================================

@app.route(
    "/admin/documents",
    methods=[
        "GET",
        "POST"
    ]
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

            price = float(
                price_raw or 0
            )

        except ValueError:

            price = 0

        if price < 0:
            price = 0

        if (
            not uploaded
            or
            not uploaded.filename
            or
            not title
        ):

            flash(
                "Title and document are required."
            )

            return redirect(
                url_for(
                    "admin_documents"
                )
            )

        filename = clean_filename(
            uploaded.filename
        )

        extension = file_extension(
            filename
        )

        if (
            extension
            not in ALLOWED_DOCUMENT_EXTENSIONS
        ):

            flash(
                "This file type is not allowed."
            )

            return redirect(
                url_for(
                    "admin_documents"
                )
            )

        file_bytes = uploaded.read()

        if not file_bytes:

            flash(
                "The uploaded file is empty."
            )

            return redirect(
                url_for(
                    "admin_documents"
                )
            )

        if len(file_bytes) > MAX_FILE_SIZE:

            flash(
                "File is too large. Maximum is 10 MB."
            )

            return redirect(
                url_for(
                    "admin_documents"
                )
            )

        # ====================================================
        # VALIDATE RECIPIENT
        # ====================================================

        if recipient_id:

            if not valid_uuid(
                recipient_id
            ):

                flash(
                    "Invalid student selected."
                )

                return redirect(
                    url_for(
                        "admin_documents"
                    )
                )

            recipient = db_select(
                "profiles",
                filters={
                    "id":
                        f"eq.{recipient_id}",

                    "role":
                        "eq.student"
                },
                limit=1
            )

            if not recipient:

                flash(
                    "Selected student does not exist."
                )

                return redirect(
                    url_for(
                        "admin_documents"
                    )
                )

        # ====================================================
        # UPLOAD TO STORAGE
        # ====================================================

        storage_path = upload_storage(
            file_bytes,
            filename,
            uploaded.content_type
        )

        if not storage_path:

            flash(
                "Document upload failed. Check Supabase Storage."
            )

            return redirect(
                url_for(
                    "admin_documents"
                )
            )

        document_id = str(
            uuid.uuid4()
        )

        document_data = {

            "id":
                document_id,

            "title":
                title,

            "description":
                description,

            "filename":
                filename,

            "mime_type":
                (
                    uploaded.content_type
                    or
                    "application/octet-stream"
                ),

            "storage_path":
                storage_path,

            "price":
                price,

            "is_paid":
                price > 0,

            "status":
                "sent",

            "is_read":
                False,

            "created_by":
                session["user_id"],

            "created_at":
                utc_now()
        }

        # IMPORTANT:
        #
        # If recipient_id is blank,
        # it remains NULL.
        #
        # NULL = General Library
        #
        # Otherwise it becomes a private
        # document for that student.

        if recipient_id:

            document_data[
                "recipient_id"
            ] = recipient_id

        result = db_insert(
            "documents",
            document_data
        )

        if result:

            # =================================================
            # NOTIFICATION
            # =================================================

            if recipient_id:

                db_insert(
                    "notifications",
                    {
                        "id":
                            str(
                                uuid.uuid4()
                            ),

                        "user_id":
                            recipient_id,

                        "title":
                            "New document received",

                        "message":
                            title,

                        "is_read":
                            False,

                        "created_at":
                            utc_now()
                    },
                    returning=False
                )

            log_activity(
                "document_uploaded",
                title
            )

            flash(
                "Document uploaded successfully."
            )

        else:

            # =================================================
            # CLEANUP STORAGE IF DB INSERT FAILS
            # =================================================

            delete_storage_file(
                storage_path
            )

            flash(
                "Document record could not be created."
            )

        return redirect(
            url_for(
                "admin_documents"
            )
        )

    # ========================================================
    # STUDENTS
    # ========================================================

    users = db_select(
        "profiles",
        filters={
            "role":
                "eq.student"
        },
        select=(
            "id,name,email"
        ),
        order="name.asc",
        limit=500
    )

    # ========================================================
    # DOCUMENTS
    # ========================================================

    docs = db_select(
        "documents",
        order="created_at.desc",
        limit=500
    )

    options = ""

    for user in users:

        options += f"""

<option
value="{escape(
    str(
        user.get(
            "id",
            ""
        )
    )
)}">

{escape(
    user.get(
        "name",
        ""
    )
)}

—
{escape(
    user.get(
        "email",
        ""
    )
)}

</option>

"""

    content = f"""

<div class="card">

<h2>
Upload Academic Document
</h2>

<p class="small">

Choose
<strong>
General Library
</strong>
to make the document available to all
logged-in students.

Choose a student to make it available
only to that student.

</p>

<form
method="POST"
enctype="multipart/form-data"
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
name="description"
></textarea>

<label>
Recipient
</label>

<select
name="recipient_id"
>

<option value="">
General Library — All Students
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

<label>
File
</label>

<input
type="file"
name="file"
required
>

<p class="small">

Maximum file size:
10 MB.

<br>

Allowed:
PDF, DOC, DOCX, PPT, PPTX,
XLS, XLSX, TXT, CSV, JPG,
JPEG and PNG.

</p>

<button type="submit">
Upload Document
</button>

</form>

</div>

<div class="card">

<h2>
Uploaded Documents
</h2>

"""

    if not docs:

        content += """

<p>
No documents have been uploaded yet.
</p>

"""

    for document in docs:

        price = (
            document.get(
                "price",
                0
            )
            or
            0
        )

        try:

            price = float(
                price
            )

        except Exception:

            price = 0

        if document.get(
            "recipient_id"
        ):

            access = (
                "Private student document"
            )

        else:

            access = (
                "General Library"
            )

        content += f"""

<div class="file-card">

<strong>

{escape(
    document.get(
        "title",
        ""
    )
)}

</strong>

<p class="small">

{escape(access)}

<br>

File:
{escape(
    document.get(
        "filename",
        ""
    )
)}

<br>

Price:
K{price:.2f}

<br>

Status:
{escape(
    str(
        document.get(
            "status",
            ""
        )
    )
)}

</p>

<a
class="btn"
href="/documents/{document.get('id')}">
Open
</a>

</div>

"""

    content += """
</div>
"""

    return page(
        content,
        "Admin Documents"
    )


# ============================================================
# DELETE STORAGE FILE
# ============================================================

def delete_storage_file(
    path
):

    if not path:
        return False

    if ".." in path:
        return False

    url = (
        f"{SUPABASE_URL}"
        f"/storage/v1/object/"
        f"{STORAGE_BUCKET}/"
        f"{path}"
    )

    try:

        response = requests.delete(
            url,
            headers=supabase_headers(True),
            timeout=30
        )

        return bool(
            response
            and
            response.ok
        )

    except requests.RequestException:

        return False


# ============================================================
# ADMIN USERS
# ============================================================

@app.route("/admin/users")
@admin_required
def admin_users():

    users = db_select(
        "profiles",
        select=(
            "id,name,email,role,created_at"
        ),
        order="created_at.desc",
        limit=500
    )

    content = """

<div class="card">

<h2>
Registered Users
</h2>

"""

    if not users:

        content += """

<p>
No registered users found.
</p>

"""

    for user in users:

        content += f"""

<div class="card">

<strong>
{escape(
    user.get(
        "name",
        ""
    )
)}
</strong>

<p>
{escape(
    user.get(
        "email",
        ""
    )
)}
</p>

<span class="badge">
{escape(
    user.get(
        "role",
        ""
    )
)}
</span>

</div>

"""

    content += """
</div>
"""

    return page(
        content,
        "Users"
    )


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

<h2>
System Activity Logs
</h2>

<p class="small">
Visible to administrators only.
</p>

</div>

"""

    if not logs:

        content += """

<div class="card">

<p>
No activity logs found.
</p>

</div>

"""

    for log in logs:

        content += f"""

<div class="card">

<strong>
{escape(
    log.get(
        "action",
        ""
    )
)}
</strong>

<p>
{escape(
    log.get(
        "description",
        ""
    )
)}
</p>

<span class="small">
{escape(
    str(
        log.get(
            "created_at",
            ""
        )
    )
)}
</span>

</div>

"""

    return page(
        content,
        "Admin Logs"
    )


# ============================================================
# QUESTION PDF
# ============================================================

@app.route(
    "/questions/<question_id>/pdf"
)
@login_required
def question_pdf(
    question_id
):

    if not valid_uuid(
        question_id
    ):

        abort(404)

    rows = db_select(
        "questions",
        filters={
            "id":
                f"eq.{question_id}"
        },
        limit=1
    )

    if not rows:

        abort(404)

    question = rows[0]

    user = current_user()

    if not user:

        abort(403)

    if (
        user.get("role")
        !=
        "admin"
        and
        question.get(
            "student_id"
        )
        !=
        session["user_id"]
    ):

        abort(403)

    body = (
        "Question:\n"
        +
        question.get(
            "question",
            ""
        )
        +
        "\n\n"
        +
        "Answer:\n"
        +
        (
            question.get(
                "answer"
            )
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
                ),

            "Generated":
                utc_now()
        }
    )

    log_activity(
        "question_pdf",
        question_id
    )

    return send_file(
        pdf,
        as_attachment=True,
        download_name=(
            "koja-answer.pdf"
        ),
        mimetype=(
            "application/pdf"
        )
    )


# ============================================================
# HEALTH CHECK
# ============================================================

@app.route("/health")
def health():

    supabase_configured = bool(
        SUPABASE_URL
        and
        SUPABASE_SERVICE_KEY
        and
        "YOUR-PROJECT"
        not in SUPABASE_URL
    )

    return {
        "app":
            APP_NAME,

        "status":
            "online",

        "year":
            2026,

        "supabase":
            (
                "configured"
                if supabase_configured
                else
                "not_configured"
            ),

        "storage_bucket":
            STORAGE_BUCKET,

        "max_upload_mb":
            10
    }


# ============================================================
# ERROR HANDLERS
# ============================================================

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
this page or document.
</p>

<a class="btn"
href="/">
Return Home
</a>

</div>

""",
        "Access Denied"
    ), 403


@app.errorhandler(404)
def not_found(error):

    return page(
        """

<div class="card">

<h2>
Page Not Found
</h2>

<p>
The requested resource does not exist.
</p>

<a class="btn"
href="/">
Return Home
</a>

</div>

""",
        "Not Found"
    ), 404


@app.errorhandler(413)
def too_large(error):

    return page(
        """

<div class="card">

<h2>
File Too Large
</h2>

<p>
The maximum upload size is 10 MB.
</p>

<a class="btn"
href="/admin/documents">
Return to Documents
</a>

</div>

""",
        "File Too Large"
    ), 413


@app.errorhandler(500)
def internal_error(error):

    logging.exception(
        "Internal server error"
    )

    return page(
        """

<div class="card">

<h2>
KOJA AFRICA Error
</h2>

<p>
Something went wrong while processing
your request.
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

    print(
        "KOJA AFRICA"
    )

    print(
        "Knowledge • Questions • Answers"
    )

    print("=" * 60)

    print(
        f"Storage bucket: "
        f"{STORAGE_BUCKET}"
    )

    print(
        "Checking Supabase configuration..."
    )

    if (
        SUPABASE_URL
        and
        SUPABASE_SERVICE_KEY
        and
        "YOUR-PROJECT"
        not in SUPABASE_URL
    ):

        print(
            "Supabase configuration detected."
        )

        print(
            "Checking Storage bucket..."
        )

        ensure_storage_bucket()

    else:

        print(
            "WARNING: Supabase environment variables "
            "are not configured."
        )

    print(
        f"Running on port {port}"
    )

    app.run(
        host=host,
        port=port,
        debug=False
    )

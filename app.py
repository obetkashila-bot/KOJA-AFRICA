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
# CONFIGURATION
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

SECRET_KEY = os.getenv(
    "SECRET_KEY",
    secrets.token_hex(32)
)

ADMIN_UUID = os.getenv(
    "ADMIN_UUID",
    "fea4ac9a-97a1-4fcf-b5cb-870843dc48dd"
)

# IMPORTANT:
# Your actual Supabase bucket is koja-files
STORAGE_BUCKET = os.getenv(
    "STORAGE_BUCKET",
    "koja-files"
)

MAX_FILE_SIZE = int(
    os.getenv(
        "MAX_FILE_SIZE",
        "10485760"
    )
)


# ============================================================
# FLASK
# ============================================================

app = Flask(__name__)

app.secret_key = SECRET_KEY

app.config["MAX_CONTENT_LENGTH"] = MAX_FILE_SIZE

logging.basicConfig(
    level=logging.INFO
)

logger = logging.getLogger("koja")


# ============================================================
# SUPABASE HEADERS
# ============================================================

def supabase_headers():
    return {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
    }


def storage_headers(content_type=None):
    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    }

    if content_type:
        headers["Content-Type"] = content_type

    return headers


# ============================================================
# SUPABASE DATABASE HELPERS
# ============================================================

def supabase_get(table, params=None):
    url = f"{SUPABASE_URL}/rest/v1/{table}"

    response = requests.get(
        url,
        headers=supabase_headers(),
        params=params or {},
        timeout=30,
    )

    return response


def supabase_post(table, data):
    url = f"{SUPABASE_URL}/rest/v1/{table}"

    headers = supabase_headers()
    headers["Prefer"] = "return=representation"

    response = requests.post(
        url,
        headers=headers,
        json=data,
        timeout=30,
    )

    return response


def supabase_patch(table, filters, data):
    url = f"{SUPABASE_URL}/rest/v1/{table}"

    params = {}

    for key, value in filters.items():
        params[key] = f"eq.{value}"

    headers = supabase_headers()
    headers["Prefer"] = "return=representation"

    response = requests.patch(
        url,
        headers=headers,
        params=params,
        json=data,
        timeout=30,
    )

    return response


def supabase_delete(table, filters):
    url = f"{SUPABASE_URL}/rest/v1/{table}"

    params = {}

    for key, value in filters.items():
        params[key] = f"eq.{value}"

    response = requests.delete(
        url,
        headers=supabase_headers(),
        params=params,
        timeout=30,
    )

    return response


# ============================================================
# AUTHENTICATION
# ============================================================

def auth_signup(email, password):
    url = f"{SUPABASE_URL}/auth/v1/signup"

    response = requests.post(
        url,
        headers={
            "apikey": SUPABASE_SERVICE_KEY,
            "Content-Type": "application/json",
        },
        json={
            "email": email,
            "password": password,
        },
        timeout=30,
    )

    return response


def auth_login(email, password):
    url = (
        f"{SUPABASE_URL}/auth/v1/token"
        "?grant_type=password"
    )

    response = requests.post(
        url,
        headers={
            "apikey": SUPABASE_SERVICE_KEY,
            "Content-Type": "application/json",
        },
        json={
            "email": email,
            "password": password,
        },
        timeout=30,
    )

    return response


def auth_user(access_token):
    url = f"{SUPABASE_URL}/auth/v1/user"

    return requests.get(
        url,
        headers={
            "apikey": SUPABASE_SERVICE_KEY,
            "Authorization": f"Bearer {access_token}",
        },
        timeout=30,
    )


# ============================================================
# CURRENT USER
# ============================================================

def current_user():
    return session.get("user")


def is_logged_in():
    return current_user() is not None


def is_admin():
    user = current_user()

    if not user:
        return False

    return str(user.get("id")) == str(ADMIN_UUID)


# ============================================================
# DECORATORS
# ============================================================

def login_required(function):

    @wraps(function)
    def wrapper(*args, **kwargs):

        if not is_logged_in():
            flash(
                "Please log in first.",
                "warning"
            )

            return redirect(
                url_for("login")
            )

        return function(*args, **kwargs)

    return wrapper


def admin_required(function):

    @wraps(function)
    def wrapper(*args, **kwargs):

        if not is_logged_in():
            flash(
                "Please log in first.",
                "warning"
            )

            return redirect(
                url_for("login")
            )

        if not is_admin():
            abort(403)

        return function(*args, **kwargs)

    return wrapper


# ============================================================
# PROFILE
# ============================================================

def get_profile(user_id):

    response = supabase_get(
        "profiles",
        {
            "id": f"eq.{user_id}",
            "select": "*",
            "limit": "1",
        }
    )

    if response.status_code != 200:
        return None

    rows = response.json()

    if not rows:
        return None

    return rows[0]


def ensure_profile(user_id, email):

    profile = get_profile(user_id)

    if profile:
        return profile

    role = (
        "admin"
        if str(user_id) == str(ADMIN_UUID)
        else "student"
    )

    response = supabase_post(
        "profiles",
        {
            "id": user_id,
            "name": email.split("@")[0],
            "email": email,
            "role": role,
        }
    )

    if response.status_code not in (200, 201):
        logger.error(
            "Profile creation failed: %s",
            response.text
        )

        return None

    rows = response.json()

    return rows[0] if rows else None


# ============================================================
# DOCUMENT HELPERS
# ============================================================

DOCUMENT_TYPES = [
    ("academic", "Academic"),
    ("assignment", "Assignment"),
    ("notes", "Notes"),
    ("past_paper", "Past Paper"),
    ("report", "Report"),
    ("answer", "Answer"),
    ("announcement", "Announcement"),
    ("other", "Other"),
]


def get_documents(search=""):

    params = {
        "select": "*",
        "is_active": "eq.true",
        "order": "created_at.desc",
    }

    response = supabase_get(
        "documents",
        params
    )

    if response.status_code != 200:
        logger.error(
            "Documents error: %s",
            response.text
        )

        return []

    documents = response.json()

    search = search.strip().lower()

    if search:

        filtered = []

        for doc in documents:

            text = " ".join([
                str(doc.get("title", "")),
                str(doc.get("description", "")),
                str(doc.get("subject", "")),
                str(doc.get("course", "")),
                str(doc.get("class_level", "")),
                str(doc.get("document_type", "")),
            ]).lower()

            if search in text:
                filtered.append(doc)

        return filtered

    return documents


def get_document(document_id):

    response = supabase_get(
        "documents",
        {
            "id": f"eq.{document_id}",
            "select": "*",
            "limit": "1",
        }
    )

    if response.status_code != 200:
        return None

    rows = response.json()

    return rows[0] if rows else None


# ============================================================
# DOCUMENT RECORD
# ============================================================

def create_document_record(
    document_id,
    user_id,
    action
):

    ip_address = request.headers.get(
        "X-Forwarded-For",
        request.remote_addr
    )

    user_agent = request.headers.get(
        "User-Agent",
        ""
    )

    data = {
        "document_id": document_id,
        "user_id": user_id,
        "action": action,
        "ip_address": ip_address,
        "user_agent": user_agent,
    }

    response = supabase_post(
        "document_records",
        data
    )

    if response.status_code not in (200, 201):
        logger.warning(
            "Document record failed: %s",
            response.text
        )

    return response


# ============================================================
# STORAGE UPLOAD
# ============================================================

def upload_to_storage(file_storage):

    original_name = file_storage.filename

    if not original_name:
        raise ValueError(
            "No file selected."
        )

    extension = os.path.splitext(
        original_name
    )[1].lower()

    allowed_extensions = {
        ".pdf",
        ".doc",
        ".docx",
        ".ppt",
        ".pptx",
        ".txt",
        ".jpg",
        ".jpeg",
        ".png",
    }

    if extension not in allowed_extensions:
        raise ValueError(
            "Unsupported file type."
        )

    safe_name = (
        uuid.uuid4().hex
        + extension
    )

    # Folder inside the koja-files bucket
    file_path = (
        f"documents/{safe_name}"
    )

    content = file_storage.read()

    if len(content) > MAX_FILE_SIZE:
        raise ValueError(
            "File is larger than 10 MB."
        )

    content_type = (
        file_storage.mimetype
        or "application/octet-stream"
    )

    url = (
        f"{SUPABASE_URL}"
        f"/storage/v1/object/"
        f"{STORAGE_BUCKET}/"
        f"{file_path}"
    )

    response = requests.post(
        url,
        headers=storage_headers(
            content_type
        ),
        data=content,
        timeout=120,
    )

    if response.status_code not in (
        200,
        201
    ):
        logger.error(
            "Storage upload failed: %s",
            response.text
        )

        raise RuntimeError(
            "Storage upload failed: "
            + response.text
        )

    return {
        "file_path": file_path,
        "file_name": original_name,
        "file_size": len(content),
        "mime_type": content_type,
    }


# ============================================================
# STORAGE DOWNLOAD
# ============================================================

def download_from_storage(
    file_path
):

    url = (
        f"{SUPABASE_URL}"
        f"/storage/v1/object/"
        f"{STORAGE_BUCKET}/"
        f"{file_path}"
    )

    response = requests.get(
        url,
        headers=storage_headers(),
        timeout=120,
    )

    return response


# ============================================================
# DELETE FROM STORAGE
# ============================================================

def delete_from_storage(
    file_path
):

    url = (
        f"{SUPABASE_URL}"
        f"/storage/v1/object/"
        f"{STORAGE_BUCKET}/"
        f"{file_path}"
    )

    return requests.delete(
        url,
        headers=storage_headers(),
        timeout=60,
    )


# ============================================================
# UPDATE DOCUMENT COUNTERS
# ============================================================

def increment_document_counter(
    document_id,
    field
):

    if field not in (
        "view_count",
        "download_count",
    ):
        return

    document = get_document(
        document_id
    )

    if not document:
        return

    current = int(
        document.get(field, 0) or 0
    )

    supabase_patch(
        "documents",
        {
            "id": document_id
        },
        {
            field: current + 1
        }
    )


# ============================================================
# HTML TEMPLATE
# ============================================================

BASE_TEMPLATE = """
<!doctype html>
<html>
<head>

<meta charset="utf-8">

<meta name="viewport"
content="width=device-width,initial-scale=1">

<title>{{ title }} | KOJA AFRICA</title>

<style>

*{
    box-sizing:border-box;
}

body{
    margin:0;
    font-family:
    Arial,
    Helvetica,
    sans-serif;

    background:#f3f6fb;
    color:#172033;
}

nav{
    background:#0b3366;
    color:white;

    padding:16px 5%;

    display:flex;
    align-items:center;
    justify-content:space-between;

    gap:20px;

    flex-wrap:wrap;
}

.logo{
    font-size:32px;
    font-weight:900;
    letter-spacing:-2px;
}

.logo span:nth-child(1){
    color:#1687ff;
}

.logo span:nth-child(2){
    color:#20c777;
}

.logo span:nth-child(3){
    color:#e73545;
}

.logo span:nth-child(4){
    color:#3568bd;
}

.navlinks{
    display:flex;
    gap:22px;
    flex-wrap:wrap;
}

.navlinks a{
    color:white;
    text-decoration:none;
    font-weight:700;
    font-size:16px;
}

.container{
    width:92%;
    max-width:1200px;
    margin:30px auto;
}

.hero{
    background:#0b3366;
    color:white;
    padding:45px;
    border-radius:22px;
    margin-bottom:25px;
}

.hero h1{
    margin-top:0;
    font-size:38px;
}

.card{
    background:white;
    border-radius:20px;
    padding:25px;
    box-shadow:
    0 5px 20px rgba(0,0,0,.07);

    margin-bottom:22px;
}

.grid{
    display:grid;
    grid-template-columns:
    repeat(auto-fit,minmax(260px,1fr));

    gap:20px;
}

.document{
    background:white;
    border-radius:18px;
    padding:22px;

    box-shadow:
    0 4px 15px rgba(0,0,0,.06);
}

.document h3{
    margin-top:0;
}

.badge{
    display:inline-block;
    background:#e9f2ff;
    color:#0b4f99;

    padding:6px 10px;
    border-radius:20px;

    font-size:12px;
    font-weight:bold;
}

button,
.btn{
    display:inline-block;

    border:0;
    border-radius:10px;

    padding:12px 18px;

    background:#0b3366;
    color:white;

    text-decoration:none;
    font-weight:bold;

    cursor:pointer;
}

.btn.green{
    background:#168a55;
}

.btn.red{
    background:#c62828;
}

.btn.gray{
    background:#68758a;
}

input,
textarea,
select{
    width:100%;

    padding:13px;

    border:1px solid #d5dce7;

    border-radius:10px;

    font-size:16px;

    margin-top:7px;
    margin-bottom:16px;
}

textarea{
    min-height:110px;
}

label{
    font-weight:bold;
}

.alert{
    padding:15px;
    border-radius:12px;
    margin-bottom:18px;

    background:#fff1d6;
    color:#7b5100;
}

table{
    width:100%;
    border-collapse:collapse;
}

th,
td{
    padding:12px;
    border-bottom:1px solid #e5e9ef;
    text-align:left;
}

.table-wrap{
    overflow-x:auto;
}

.stat{
    font-size:30px;
    font-weight:900;
}

.small{
    color:#697589;
    font-size:14px;
}

.actions{
    display:flex;
    gap:8px;
    flex-wrap:wrap;
}

footer{
    text-align:center;
    padding:35px;
    color:#68758a;
}

@media(max-width:600px){

    .hero{
        padding:28px;
    }

    .hero h1{
        font-size:29px;
    }

    .navlinks{
        width:100%;
    }

}

</style>

</head>

<body>

<nav>

<div class="logo">
<span>k</span><span>o</span><span>j</span><span>a</span>
</div>

<div class="navlinks">

<a href="{{ url_for('home') }}">Home</a>

{% if session.get('user') %}
<a href="{{ url_for('documents') }}">Documents</a>
{% endif %}

{% if session.get('user') and session.get('is_admin') %}
<a href="{{ url_for('admin') }}">Admin</a>
<a href="{{ url_for('upload_document') }}">Upload</a>
{% endif %}

{% if session.get('user') %}
<a href="{{ url_for('logout') }}">Logout</a>
{% else %}
<a href="{{ url_for('login') }}">Login</a>
<a href="{{ url_for('register') }}">Create Account</a>
{% endif %}

</div>

</nav>

<div class="container">

{% with messages = get_flashed_messages(with_categories=true) %}

{% for category, message in messages %}

<div class="alert">
{{ message }}
</div>

{% endfor %}

{% endwith %}

{{ content|safe }}

</div>

<footer>
KOJA AFRICA — Knowledge • Questions • Answers
<br>
Academic Documents & Learning Resources
</footer>

</body>
</html>
"""


def render_page(
    title,
    content,
    **context
):

    return render_template_string(
        BASE_TEMPLATE,
        title=title,
        content=render_template_string(
            content,
            **context
        ),
        **context
    )


# ============================================================
# HOME
# ============================================================

@app.route("/")
def home():

    return render_page(
        "Home",
        """
        <div class="hero">

        <h1>KOJA AFRICA</h1>

        <p>
        Knowledge • Questions • Answers
        </p>

        <p>
        Access academic documents,
        assignments, notes, past papers
        and learning resources.
        </p>

        {% if not session.get('user') %}

        <div class="actions">

        <a class="btn"
        href="{{ url_for('login') }}">
        Login
        </a>

        <a class="btn green"
        href="{{ url_for('register') }}">
        Create Account
        </a>

        </div>

        {% else %}

        <a class="btn"
        href="{{ url_for('documents') }}">
        Open Document Library
        </a>

        {% endif %}

        </div>
        """
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

        name = request.form.get(
            "name",
            ""
        ).strip()

        if not email or not password:
            flash(
                "Email and password are required.",
                "warning"
            )

            return redirect(
                url_for("register")
            )

        if len(password) < 6:
            flash(
                "Password must contain at least 6 characters.",
                "warning"
            )

            return redirect(
                url_for("register")
            )

        response = auth_signup(
            email,
            password
        )

        if response.status_code not in (
            200,
            201
        ):
            try:
                error = response.json().get(
                    "msg"
                ) or response.json().get(
                    "message"
                ) or response.text
            except Exception:
                error = response.text

            flash(
                "Registration failed: "
                + str(error),
                "warning"
            )

            return redirect(
                url_for("register")
            )

        data = response.json()

        user = data.get("user")

        if not user:
            flash(
                "Account created. Please check your email if confirmation is required, then log in.",
                "success"
            )

            return redirect(
                url_for("login")
            )

        user_id = user.get("id")

        profile_response = supabase_post(
            "profiles",
            {
                "id": user_id,
                "name": name or email.split("@")[0],
                "email": email,
                "role": "student",
            }
        )

        if profile_response.status_code not in (
            200,
            201
        ):
            logger.warning(
                "Profile creation after registration failed: %s",
                profile_response.text
            )

        flash(
            "Account created successfully. You can now log in.",
            "success"
        )

        return redirect(
            url_for("login")
        )

    return render_page(
        "Create Account",
        """
        <div class="card">

        <h1>Create Student Account</h1>

        <form method="post">

        <label>Name</label>

        <input
        type="text"
        name="name"
        required
        placeholder="Your full name">

        <label>Email</label>

        <input
        type="email"
        name="email"
        required
        placeholder="student@example.com">

        <label>Password</label>

        <input
        type="password"
        name="password"
        required
        minlength="6"
        placeholder="Minimum 6 characters">

        <button type="submit">
        Create Account
        </button>

        </form>

        </div>
        """
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

        response = auth_login(
            email,
            password
        )

        if response.status_code != 200:

            try:
                error_data = response.json()

                error = (
                    error_data.get("error_description")
                    or error_data.get("msg")
                    or error_data.get("message")
                    or response.text
                )

            except Exception:

                error = response.text

            flash(
                "Login failed: "
                + str(error),
                "warning"
            )

            return redirect(
                url_for("login")
            )

        data = response.json()

        access_token = data.get(
            "access_token"
        )

        user = data.get(
            "user"
        )

        if not user and access_token:

            user_response = auth_user(
                access_token
            )

            if user_response.status_code == 200:
                user = user_response.json()

        if not user:
            flash(
                "Login failed. User information was not returned.",
                "warning"
            )

            return redirect(
                url_for("login")
            )

        user_id = user.get("id")

        profile = ensure_profile(
            user_id,
            user.get("email", email)
        )

        session.clear()

        session["access_token"] = access_token

        session["user"] = {
            "id": user_id,
            "email": user.get(
                "email",
                email
            ),
            "name": (
                profile.get("name")
                if profile
                else email.split("@")[0]
            ),
        }

        session["is_admin"] = (
            str(user_id)
            ==
            str(ADMIN_UUID)
        )

        flash(
            "Welcome to KOJA AFRICA.",
            "success"
        )

        return redirect(
            url_for("documents")
        )

    return render_page(
        "Login",
        """
        <div class="card">

        <h1>Login</h1>

        <form method="post">

        <label>Email</label>

        <input
        type="email"
        name="email"
        required
        placeholder="Email">

        <label>Password</label>

        <input
        type="password"
        name="password"
        required
        placeholder="Password">

        <button type="submit">
        Login
        </button>

        </form>

        <br>

        <p>
        Don't have an account?
        <a href="{{ url_for('register') }}">
        Create Account
        </a>
        </p>

        </div>
        """
    )


# ============================================================
# LOGOUT
# ============================================================

@app.route("/logout")
def logout():

    session.clear()

    flash(
        "You have been logged out.",
        "success"
    )

    return redirect(
        url_for("home")
    )


# ============================================================
# DOCUMENT LIBRARY
# ============================================================

@app.route("/documents")
@login_required
def documents():

    search = request.args.get(
        "search",
        ""
    )

    docs = get_documents(
        search
    )

    return render_page(
        "Documents",
        """
        <div class="card">

        <h1>Document Library</h1>

        <form method="get">

        <input
        type="text"
        name="search"
        value="{{ search }}"
        placeholder="Search title, subject, course...">

        <button type="submit">
        Search
        </button>

        </form>

        </div>

        <div class="grid">

        {% for doc in docs %}

        <div class="document">

        <span class="badge">
        {{ doc.document_type|replace('_',' ')|title }}
        </span>

        <h3>
        {{ doc.title }}
        </h3>

        <p>
        {{ doc.description or 'No description available.' }}
        </p>

        {% if doc.subject %}
        <p>
        <b>Subject:</b>
        {{ doc.subject }}
        </p>
        {% endif %}

        {% if doc.course %}
        <p>
        <b>Course:</b>
        {{ doc.course }}
        </p>
        {% endif %}

        {% if doc.class_level %}
        <p>
        <b>Class:</b>
        {{ doc.class_level }}
        </p>
        {% endif %}

        <p class="small">
        {{ doc.file_name }}
        </p>

        <p class="small">
        Views: {{ doc.view_count or 0 }}
        |
        Downloads: {{ doc.download_count or 0 }}
        </p>

        <div class="actions">

        <a class="btn"
        href="{{ url_for('view_document', document_id=doc.id) }}">
        View
        </a>

        <a class="btn green"
        href="{{ url_for('download_document', document_id=doc.id) }}">
        Download
        </a>

        </div>

        </div>

        {% else %}

        <div class="card">

        <h2>No documents found.</h2>

        <p>
        Try another search or ask the administrator
        to upload learning resources.
        </p>

        </div>

        {% endfor %}

        </div>
        """,
        docs=docs,
        search=search
    )


# ============================================================
# VIEW DOCUMENT
# ============================================================

@app.route(
    "/documents/<document_id>/view"
)
@login_required
def view_document(document_id):

    document = get_document(
        document_id
    )

    if not document:
        abort(404)

    increment_document_counter(
        document_id,
        "view_count"
    )

    create_document_record(
        document_id,
        current_user()["id"],
        "viewed"
    )

    response = download_from_storage(
        document["file_path"]
    )

    if response.status_code != 200:

        flash(
            "The document could not be retrieved from storage.",
            "warning"
        )

        return redirect(
            url_for("documents")
        )

    mime = document.get(
        "mime_type"
    ) or "application/octet-stream"

    return send_file(
        io.BytesIO(response.content),
        mimetype=mime,
        download_name=document["file_name"],
        as_attachment=False
    )


# ============================================================
# DOWNLOAD DOCUMENT
# ============================================================

@app.route(
    "/documents/<document_id>/download"
)
@login_required
def download_document(document_id):

    document = get_document(
        document_id
    )

    if not document:
        abort(404)

    response = download_from_storage(
        document["file_path"]
    )

    if response.status_code != 200:

        flash(
            "Download failed.",
            "warning"
        )

        return redirect(
            url_for("documents")
        )

    increment_document_counter(
        document_id,
        "download_count"
    )

    create_document_record(
        document_id,
        current_user()["id"],
        "downloaded"
    )

    return send_file(
        io.BytesIO(response.content),
        mimetype=document.get(
            "mime_type"
        ) or "application/octet-stream",
        download_name=document[
            "file_name"
        ],
        as_attachment=True
    )


# ============================================================
# ADMIN DASHBOARD
# ============================================================

@app.route("/admin")
@admin_required
def admin():

    docs = get_documents()

    total = len(docs)

    total_views = sum(
        int(
            d.get(
                "view_count",
                0
            ) or 0
        )
        for d in docs
    )

    total_downloads = sum(
        int(
            d.get(
                "download_count",
                0
            ) or 0
        )
        for d in docs
    )

    records_response = supabase_get(
        "document_records",
        {
            "select": "*",
            "order": "created_at.desc",
            "limit": "100",
        }
    )

    records = []

    if records_response.status_code == 200:
        records = records_response.json()

    return render_page(
        "Admin",
        """
        <div class="hero">

        <h1>Admin Dashboard</h1>

        <p>
        Document Management
        </p>

        <a class="btn green"
        href="{{ url_for('upload_document') }}">
        Upload Document
        </a>

        </div>

        <div class="grid">

        <div class="card">
        <div class="small">Documents</div>
        <div class="stat">{{ total }}</div>
        </div>

        <div class="card">
        <div class="small">Views</div>
        <div class="stat">{{ total_views }}</div>
        </div>

        <div class="card">
        <div class="small">Downloads</div>
        <div class="stat">{{ total_downloads }}</div>
        </div>

        </div>

        <div class="card">

        <h2>Documents</h2>

        <div class="table-wrap">

        <table>

        <tr>
        <th>Title</th>
        <th>Type</th>
        <th>Views</th>
        <th>Downloads</th>
        <th>Actions</th>
        </tr>

        {% for doc in docs %}

        <tr>

        <td>
        {{ doc.title }}
        </td>

        <td>
        {{ doc.document_type }}
        </td>

        <td>
        {{ doc.view_count or 0 }}
        </td>

        <td>
        {{ doc.download_count or 0 }}
        </td>

        <td>

        <div class="actions">

        <a class="btn"
        href="{{ url_for('view_document', document_id=doc.id) }}">
        View
        </a>

        <a class="btn gray"
        href="{{ url_for('edit_document', document_id=doc.id) }}">
        Edit
        </a>

        <form method="post"
        action="{{ url_for('delete_document', document_id=doc.id) }}"
        onsubmit="return confirm('Delete this document?');">

        <button class="btn red"
        type="submit">
        Delete
        </button>

        </form>

        </div>

        </td>

        </tr>

        {% endfor %}

        </table>

        </div>

        </div>

        <div class="card">

        <h2>Document Activity</h2>

        <div class="table-wrap">

        <table>

        <tr>
        <th>Document</th>
        <th>User</th>
        <th>Action</th>
        <th>Time</th>
        </tr>

        {% for record in records %}

        <tr>

        <td>
        {{ record.document_id }}
        </td>

        <td>
        {{ record.user_id or 'Unknown' }}
        </td>

        <td>
        {{ record.action }}
        </td>

        <td>
        {{ record.created_at }}
        </td>

        </tr>

        {% endfor %}

        </table>

        </div>

        </div>
        """,
        docs=docs,
        records=records,
        total=total,
        total_views=total_views,
        total_downloads=total_downloads
    )


# ============================================================
# UPLOAD DOCUMENT
# ============================================================

@app.route(
    "/admin/documents/upload",
    methods=["GET", "POST"]
)
@admin_required
def upload_document():

    if request.method == "POST":

        title = request.form.get(
            "title",
            ""
        ).strip()

        description = request.form.get(
            "description",
            ""
        ).strip()

        document_type = request.form.get(
            "document_type",
            "academic"
        )

        subject = request.form.get(
            "subject",
            ""
        ).strip()

        course = request.form.get(
            "course",
            ""
        ).strip()

        class_level = request.form.get(
            "class_level",
            ""
        ).strip()

        is_public = (
            request.form.get(
                "is_public"
            )
            == "on"
        )

        file = request.files.get(
            "file"
        )

        if not title:
            flash(
                "Document title is required.",
                "warning"
            )

            return redirect(
                url_for("upload_document")
            )

        if not file or not file.filename:
            flash(
                "Please select a document.",
                "warning"
            )

            return redirect(
                url_for("upload_document")
            )

        if document_type not in [
            x[0]
            for x in DOCUMENT_TYPES
        ]:
            flash(
                "Invalid document type.",
                "warning"
            )

            return redirect(
                url_for("upload_document")
            )

        try:

            storage_info = upload_to_storage(
                file
            )

            data = {
                "title": title,
                "description": description or None,
                "document_type": document_type,
                "subject": subject or None,
                "course": course or None,
                "class_level": class_level or None,
                "file_name": storage_info[
                    "file_name"
                ],
                "file_path": storage_info[
                    "file_path"
                ],
                "file_url": None,
                "file_size": storage_info[
                    "file_size"
                ],
                "mime_type": storage_info[
                    "mime_type"
                ],
                "uploaded_by": current_user()[
                    "id"
                ],
                "is_public": is_public,
                "is_active": True,
                "download_count": 0,
                "view_count": 0,
            }

            response = supabase_post(
                "documents",
                data
            )

            if response.status_code not in (
                200,
                201
            ):

                # Database insert failed,
                # therefore remove the uploaded file.
                delete_from_storage(
                    storage_info[
                        "file_path"
                    ]
                )

                logger.error(
                    "Document database insert failed: %s",
                    response.text
                )

                flash(
                    "Document metadata could not be saved: "
                    + response.text,
                    "warning"
                )

                return redirect(
                    url_for("upload_document")
                )

            rows = response.json()

            document_id = (
                rows[0]["id"]
                if rows
                else None
            )

            if document_id:

                create_document_record(
                    document_id,
                    current_user()["id"],
                    "uploaded"
                )

            flash(
                "Document uploaded successfully.",
                "success"
            )

            return redirect(
                url_for("admin")
            )

        except Exception as exc:

            logger.exception(
                "Upload error"
            )

            flash(
                "Upload failed: "
                + str(exc),
                "warning"
            )

            return redirect(
                url_for("upload_document")
            )

    return render_page(
        "Upload Document",
        """
        <div class="card">

        <h1>Upload Academic Document</h1>

        <form
        method="post"
        enctype="multipart/form-data">

        <label>Document Title</label>

        <input
        type="text"
        name="title"
        required
        placeholder="e.g. Grade 12 Biology Notes">

        <label>Description</label>

        <textarea
        name="description"
        placeholder="Describe the document..."></textarea>

        <label>Document Type</label>

        <select name="document_type">

        {% for value, label in document_types %}

        <option value="{{ value }}">
        {{ label }}
        </option>

        {% endfor %}

        </select>

        <label>Subject</label>

        <input
        type="text"
        name="subject"
        placeholder="e.g. Biology">

        <label>Course</label>

        <input
        type="text"
        name="course"
        placeholder="e.g. General Biology">

        <label>Class Level</label>

        <input
        type="text"
        name="class_level"
        placeholder="e.g. Grade 12">

        <label>Document File</label>

        <input
        type="file"
        name="file"
        required>

        <p class="small">
        Maximum file size: 10 MB.
        Supported: PDF, DOC, DOCX, PPT, PPTX,
        TXT, JPG, JPEG and PNG.
        </p>

        <label>

        <input
        type="checkbox"
        name="is_public"
        style="width:auto;">

        Make document public

        </label>

        <br><br>

        <button type="submit">
        Upload Document
        </button>

        </form>

        </div>
        """,
        document_types=DOCUMENT_TYPES
    )


# ============================================================
# EDIT DOCUMENT
# ============================================================

@app.route(
    "/admin/documents/<document_id>/edit",
    methods=["GET", "POST"]
)
@admin_required
def edit_document(document_id):

    document = get_document(
        document_id
    )

    if not document:
        abort(404)

    if request.method == "POST":

        data = {
            "title": request.form.get(
                "title",
                ""
            ).strip(),

            "description": request.form.get(
                "description",
                ""
            ).strip() or None,

            "document_type": request.form.get(
                "document_type",
                "academic"
            ),

            "subject": request.form.get(
                "subject",
                ""
            ).strip() or None,

            "course": request.form.get(
                "course",
                ""
            ).strip() or None,

            "class_level": request.form.get(
                "class_level",
                ""
            ).strip() or None,

            "is_public": (
                request.form.get(
                    "is_public"
                )
                == "on"
            ),

            "is_active": (
                request.form.get(
                    "is_active"
                )
                == "on"
            ),
        }

        response = supabase_patch(
            "documents",
            {
                "id": document_id
            },
            data
        )

        if response.status_code not in (
            200,
            204
        ):

            flash(
                "Update failed: "
                + response.text,
                "warning"
            )

            return redirect(
                url_for(
                    "edit_document",
                    document_id=document_id
                )
            )

        create_document_record(
            document_id,
            current_user()["id"],
            "updated"
        )

        flash(
            "Document updated successfully.",
            "success"
        )

        return redirect(
            url_for("admin")
        )

    return render_page(
        "Edit Document",
        """
        <div class="card">

        <h1>Edit Document</h1>

        <form method="post">

        <label>Title</label>

        <input
        type="text"
        name="title"
        required
        value="{{ document.title }}">

        <label>Description</label>

        <textarea
        name="description">{{ document.description or '' }}</textarea>

        <label>Document Type</label>

        <select name="document_type">

        {% for value, label in document_types %}

        <option
        value="{{ value }}"
        {% if document.document_type == value %}
        selected
        {% endif %}>

        {{ label }}

        </option>

        {% endfor %}

        </select>

        <label>Subject</label>

        <input
        type="text"
        name="subject"
        value="{{ document.subject or '' }}">

        <label>Course</label>

        <input
        type="text"
        name="course"
        value="{{ document.course or '' }}">

        <label>Class Level</label>

        <input
        type="text"
        name="class_level"
        value="{{ document.class_level or '' }}">

        <label>

        <input
        type="checkbox"
        name="is_public"
        style="width:auto;"
        {% if document.is_public %}
        checked
        {% endif %}>

        Public

        </label>

        <br>

        <label>

        <input
        type="checkbox"
        name="is_active"
        style="width:auto;"
        {% if document.is_active %}
        checked
        {% endif %}>

        Active

        </label>

        <br><br>

        <button type="submit">
        Save Changes
        </button>

        </form>

        </div>
        """,
        document=document,
        document_types=DOCUMENT_TYPES
    )


# ============================================================
# DELETE DOCUMENT
# ============================================================

@app.route(
    "/admin/documents/<document_id>/delete",
    methods=["POST"]
)
@admin_required
def delete_document(document_id):

    document = get_document(
        document_id
    )

    if not document:
        abort(404)

    file_path = document.get(
        "file_path"
    )

    # Delete storage object first.
    if file_path:
        storage_response = delete_from_storage(
            file_path
        )

        if storage_response.status_code not in (
            200,
            204
        ):
            logger.warning(
                "Storage deletion failed: %s",
                storage_response.text
            )

    # The database table uses
    # document_records.document_id
    # with ON DELETE SET NULL.
    #
    # Therefore audit records are preserved.

    response = supabase_delete(
        "documents",
        {
            "id": document_id
        }
    )

    if response.status_code not in (
        200,
        204
    ):

        flash(
            "Database deletion failed: "
            + response.text,
            "warning"
        )

        return redirect(
            url_for("admin")
        )

    flash(
        "Document deleted successfully.",
        "success"
    )

    return redirect(
        url_for("admin")
    )


# ============================================================
# ADMIN PDF REPORT
# ============================================================

@app.route(
    "/admin/documents/report.pdf"
)
@admin_required
def document_report():

    docs = get_documents()

    buffer = io.BytesIO()

    styles = getSampleStyleSheet()

    title_style = styles["Title"]

    title_style.alignment = TA_CENTER

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=35,
        leftMargin=35,
        topMargin=35,
        bottomMargin=35,
    )

    story = []

    story.append(
        Paragraph(
            "KOJA AFRICA",
            title_style
        )
    )

    story.append(
        Spacer(1, 10)
    )

    story.append(
        Paragraph(
            "Document Management Report",
            styles["Heading2"]
        )
    )

    story.append(
        Spacer(1, 15)
    )

    data = [
        [
            "Title",
            "Type",
            "Subject",
            "Views",
            "Downloads",
        ]
    ]

    for document in docs:

        data.append(
            [
                document.get(
                    "title",
                    ""
                )[:35],

                document.get(
                    "document_type",
                    ""
                ),

                document.get(
                    "subject",
                    ""
                ) or "",

                str(
                    document.get(
                        "view_count",
                        0
                    )
                ),

                str(
                    document.get(
                        "download_count",
                        0
                    )
                ),
            ]
        )

    table = Table(
        data,
        repeatRows=1
    )

    table.setStyle(
        TableStyle(
            [
                (
                    "BACKGROUND",
                    (0, 0),
                    (-1, 0),
                    colors.HexColor(
                        "#0b3366"
                    )
                ),

                (
                    "TEXTCOLOR",
                    (0, 0),
                    (-1, 0),
                    colors.white
                ),

                (
                    "GRID",
                    (0, 0),
                    (-1, -1),
                    0.5,
                    colors.grey
                ),

                (
                    "FONTNAME",
                    (0, 0),
                    (-1, 0),
                    "Helvetica-Bold"
                ),

                (
                    "FONTSIZE",
                    (0, 0),
                    (-1, -1),
                    7
                ),

                (
                    "VALIGN",
                    (0, 0),
                    (-1, -1),
                    "TOP"
                ),
            ]
        )
    )

    story.append(table)

    story.append(
        Spacer(1, 20)
    )

    story.append(
        Paragraph(
            "Generated by KOJA AFRICA",
            styles["Normal"]
        )
    )

    doc.build(story)

    buffer.seek(0)

    return send_file(
        buffer,
        mimetype="application/pdf",
        as_attachment=True,
        download_name="koja-document-report.pdf"
    )


# ============================================================
# 403
# ============================================================

@app.errorhandler(403)
def forbidden(error):

    return render_page(
        "Access Denied",
        """
        <div class="card">

        <h1>Access Denied</h1>

        <p>
        You do not have administrator permission
        to access this page.
        </p>

        <a class="btn"
        href="{{ url_for('home') }}">
        Return Home
        </a>

        </div>
        """
    ), 403


# ============================================================
# 404
# ============================================================

@app.errorhandler(404)
def not_found(error):

    return render_page(
        "Not Found",
        """
        <div class="card">

        <h1>Page Not Found</h1>

        <a class="btn"
        href="{{ url_for('home') }}">
        Return Home
        </a>

        </div>
        """
    ), 404


# ============================================================
# 413
# ============================================================

@app.errorhandler(413)
def too_large(error):

    return render_page(
        "File Too Large",
        """
        <div class="card">

        <h1>File Too Large</h1>

        <p>
        The maximum allowed document size is 10 MB.
        </p>

        </div>
        """
    ), 413


# ============================================================
# GENERAL ERROR
# ============================================================

@app.errorhandler(500)
def server_error(error):

    logger.exception(
        "Internal server error"
    )

    return render_page(
        "Server Error",
        """
        <div class="card">

        <h1>Server Error</h1>

        <p>
        Something went wrong on the server.
        Please try again.
        </p>

        </div>
        """
    ), 500


# ============================================================
# HEALTH CHECK
# ============================================================

@app.route("/health")
def health():

    return {
        "status": "ok",
        "application": "KOJA AFRICA",
        "storage_bucket": STORAGE_BUCKET,
        "documents_system": True,
    }


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

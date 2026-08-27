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

from werkzeug.utils import secure_filename

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

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")

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

STORAGE_BUCKET = os.getenv(
    "STORAGE_BUCKET",
    "documents"
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


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO
)

logger = logging.getLogger(
    "koja"
)


# ============================================================
# SUPABASE HEADERS
# ============================================================

def supabase_headers():

    return {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization":
            f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type":
            "application/json",
    }


def supabase_storage_headers():

    return {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization":
            f"Bearer {SUPABASE_SERVICE_KEY}",
    }


# ============================================================
# SUPABASE REST HELPERS
# ============================================================

def supabase_get(
    table,
    params=None
):

    url = (
        f"{SUPABASE_URL}"
        f"/rest/v1/{table}"
    )

    response = requests.get(
        url,
        headers=supabase_headers(),
        params=params,
        timeout=30
    )

    if not response.ok:

        logger.error(
            "Supabase GET error: %s",
            response.text
        )

        raise RuntimeError(
            response.text
        )

    return response.json()


def supabase_insert(
    table,
    data,
    return_data=True
):

    url = (
        f"{SUPABASE_URL}"
        f"/rest/v1/{table}"
    )

    headers = supabase_headers()

    if return_data:

        headers["Prefer"] = (
            "return=representation"
        )

    response = requests.post(
        url,
        headers=headers,
        json=data,
        timeout=30
    )

    if not response.ok:

        logger.error(
            "Supabase INSERT error: %s",
            response.text
        )

        raise RuntimeError(
            response.text
        )

    if not return_data:

        return True

    return response.json()


def supabase_update(
    table,
    filters,
    data
):

    url = (
        f"{SUPABASE_URL}"
        f"/rest/v1/{table}"
    )

    params = {}

    params.update(filters)

    headers = supabase_headers()

    headers["Prefer"] = (
        "return=representation"
    )

    response = requests.patch(
        url,
        headers=headers,
        params=params,
        json=data,
        timeout=30
    )

    if not response.ok:

        logger.error(
            "Supabase UPDATE error: %s",
            response.text
        )

        raise RuntimeError(
            response.text
        )

    return response.json()


def supabase_delete(
    table,
    filters
):

    url = (
        f"{SUPABASE_URL}"
        f"/rest/v1/{table}"
    )

    response = requests.delete(
        url,
        headers=supabase_headers(),
        params=filters,
        timeout=30
    )

    if not response.ok:

        logger.error(
            "Supabase DELETE error: %s",
            response.text
        )

        raise RuntimeError(
            response.text
        )

    return True


# ============================================================
# SUPABASE AUTH
# ============================================================

def auth_login(
    email,
    password
):

    url = (
        f"{SUPABASE_URL}"
        "/auth/v1/token"
    )

    response = requests.post(
        url,
        headers={
            "apikey":
                SUPABASE_SERVICE_KEY,
            "Content-Type":
                "application/json",
        },
        params={
            "grant_type": "password"
        },
        json={
            "email": email,
            "password": password
        },
        timeout=30
    )

    if not response.ok:

        logger.warning(
            "Login failed: %s",
            response.text
        )

        return None

    return response.json()


def auth_register(
    email,
    password
):

    url = (
        f"{SUPABASE_URL}"
        "/auth/v1/signup"
    )

    response = requests.post(
        url,
        headers={
            "apikey":
                SUPABASE_SERVICE_KEY,
            "Content-Type":
                "application/json",
        },
        json={
            "email": email,
            "password": password
        },
        timeout=30
    )

    if not response.ok:

        logger.warning(
            "Registration failed: %s",
            response.text
        )

        return None, response.text

    return response.json(), None


# ============================================================
# CURRENT USER
# ============================================================

def current_user_id():

    return session.get(
        "user_id"
    )


def current_user():

    uid = current_user_id()

    if not uid:
        return None

    try:

        rows = supabase_get(
            "profiles",
            {
                "select":
                    "id,name,email,role,created_at",
                "id":
                    f"eq.{uid}",
                "limit":
                    "1"
            }
        )

        if rows:

            return rows[0]

    except Exception as exc:

        logger.error(
            "Profile lookup failed: %s",
            exc
        )

    return None


# ============================================================
# DECORATORS
# ============================================================

def login_required(function):

    @wraps(function)
    def wrapper(*args, **kwargs):

        if not current_user_id():

            flash(
                "Please log in first.",
                "warning"
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

        uid = current_user_id()

        if uid != ADMIN_UUID:

            flash(
                "Administrator access required.",
                "danger"
            )

            return redirect(
                url_for("home")
            )

        return function(
            *args,
            **kwargs
        )

    return wrapper


# ============================================================
# ACTIVITY LOGGER
# ============================================================

def record_document_action(
    document_id,
    action
):

    uid = current_user_id()

    if not uid:
        return

    try:

        supabase_insert(
            "document_records",
            {
                "document_id":
                    document_id,

                "user_id":
                    uid,

                "action":
                    action,

                "ip_address":
                    request.headers.get(
                        "X-Forwarded-For",
                        request.remote_addr
                    ),

                "user_agent":
                    request.headers.get(
                        "User-Agent",
                        ""
                    ),

                "created_at":
                    datetime.now(
                        timezone.utc
                    ).isoformat()
            },
            return_data=False
        )

    except Exception as exc:

        logger.error(
            "Activity logging failed: %s",
            exc
        )


# ============================================================
# STORAGE UPLOAD
# ============================================================

def upload_storage(
    file,
    path
):

    url = (
        f"{SUPABASE_URL}"
        f"/storage/v1/object/"
        f"{STORAGE_BUCKET}/"
        f"{path}"
    )

    headers = supabase_storage_headers()

    headers["Content-Type"] = (
        file.content_type
        or "application/octet-stream"
    )

    response = requests.post(
        url,
        headers=headers,
        data=file.stream,
        timeout=120
    )

    if not response.ok:

        logger.error(
            "Storage upload error: %s",
            response.text
        )

        raise RuntimeError(
            response.text
        )

    return path


# ============================================================
# STORAGE DOWNLOAD
# ============================================================

def download_storage(
    path
):

    url = (
        f"{SUPABASE_URL}"
        f"/storage/v1/object/"
        f"{STORAGE_BUCKET}/"
        f"{path}"
    )

    response = requests.get(
        url,
        headers=supabase_storage_headers(),
        timeout=120
    )

    if not response.ok:

        logger.error(
            "Storage download error: %s",
            response.text
        )

        raise RuntimeError(
            response.text
        )

    return response.content


# ============================================================
# HTML TEMPLATE
# ============================================================

BASE_HTML = """
<!DOCTYPE html>

<html lang="en">

<head>

<meta charset="UTF-8">

<meta
name="viewport"
content="width=device-width,initial-scale=1.0"
>

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
    background:#f4f7fb;
    color:#172033;
}

nav{
    background:#082b59;
    color:white;
    padding:15px 20px;
    display:flex;
    justify-content:space-between;
    align-items:center;
    gap:15px;
    flex-wrap:wrap;
}

.logo{
    font-size:24px;
    font-weight:800;
    letter-spacing:1px;
}

.logo span:nth-child(1){
    color:#1687ff;
}

.logo span:nth-child(2){
    color:#20b96b;
}

.logo span:nth-child(3){
    color:#e63946;
}

.logo span:nth-child(4){
    color:#173f91;
}

nav a{
    color:white;
    text-decoration:none;
    margin:4px 7px;
    font-weight:600;
}

.container{
    width:min(1180px,94%);
    margin:25px auto;
}

.hero{
    background:linear-gradient(
        135deg,
        #082b59,
        #0d4d91
    );
    color:white;
    border-radius:18px;
    padding:35px;
    margin-bottom:25px;
}

.hero h1{
    margin-top:0;
    font-size:36px;
}

.card{
    background:white;
    border-radius:16px;
    padding:22px;
    margin-bottom:20px;
    box-shadow:
        0 5px 25px
        rgba(0,0,0,.06);
}

.grid{
    display:grid;
    grid-template-columns:
        repeat(auto-fit,minmax(240px,1fr));
    gap:18px;
}

.stat{
    background:white;
    border-radius:15px;
    padding:20px;
    box-shadow:
        0 4px 18px
        rgba(0,0,0,.05);
}

.stat strong{
    display:block;
    font-size:30px;
    color:#0d4d91;
}

input,
select,
textarea{
    width:100%;
    padding:12px;
    margin:6px 0 14px;
    border:1px solid #d7deea;
    border-radius:9px;
    font-size:15px;
}

textarea{
    min-height:100px;
}

button,
.btn{
    border:0;
    background:#0d4d91;
    color:white;
    padding:11px 17px;
    border-radius:9px;
    cursor:pointer;
    text-decoration:none;
    display:inline-block;
    font-weight:600;
}

.btn-green{
    background:#168a55;
}

.btn-red{
    background:#c62828;
}

.btn-dark{
    background:#172033;
}

table{
    width:100%;
    border-collapse:collapse;
}

th,
td{
    padding:12px;
    border-bottom:1px solid #e8edf4;
    text-align:left;
}

th{
    background:#f1f5fa;
}

.badge{
    display:inline-block;
    padding:5px 9px;
    border-radius:20px;
    background:#e8f0ff;
    color:#174d91;
    font-size:12px;
    font-weight:bold;
}

.flash{
    padding:13px 16px;
    border-radius:10px;
    margin-bottom:15px;
}

.flash.success{
    background:#dff7e9;
    color:#126332;
}

.flash.danger{
    background:#fde4e4;
    color:#8d1515;
}

.flash.warning{
    background:#fff2cf;
    color:#795600;
}

.flash.info{
    background:#e0efff;
    color:#145287;
}

.document{
    height:100%;
}

.document h3{
    margin-top:0;
}

.muted{
    color:#687386;
    font-size:14px;
}

footer{
    text-align:center;
    padding:30px;
    color:#687386;
}

@media(max-width:700px){

    .hero{
        padding:24px;
    }

    .hero h1{
        font-size:28px;
    }

    table{
        display:block;
        overflow-x:auto;
    }

    nav{
        align-items:flex-start;
    }

}

</style>

</head>

<body>

<nav>

<div class="logo">
<span>k</span><span>o</span><span>j</span><span>a</span>
</div>

<div>

<a href="{{ url_for('home') }}">
Home
</a>

{% if session.get('user_id') %}

<a href="{{ url_for('documents') }}">
Documents
</a>

{% if session.get('user_id') == admin_uuid %}

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

{% with messages = get_flashed_messages(
    with_categories=true
) %}

{% for category,message in messages %}

<div class="flash {{ category }}">
{{ message }}
</div>

{% endfor %}

{% endwith %}


{{ content|safe }}

</div>


<footer>

<strong>KOJA AFRICA</strong><br>

Knowledge • Questions • Answers

</footer>

</body>

</html>
"""


# ============================================================
# RENDER PAGE
# ============================================================

def page(
    title,
    content,
    **context
):

    context["title"] = title

    context["admin_uuid"] = ADMIN_UUID

    context["current_user"] = current_user()

    context["session"] = session

    return render_template_string(
        BASE_HTML,
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

    return page(
        "Home",
        """
        <section class="hero">

            <h1>
                KOJA AFRICA
            </h1>

            <p>
                Knowledge • Questions • Answers
            </p>

            <p>
                Access academic documents,
                assignments, notes,
                past papers and learning
                resources.
            </p>

            {% if not session.get('user_id') %}

            <a class="btn"
               href="{{ url_for('login') }}">
                Login
            </a>

            <a class="btn btn-green"
               href="{{ url_for('register') }}">
                Create Account
            </a>

            {% else %}

            <a class="btn"
               href="{{ url_for('documents') }}">
                Open Document Library
            </a>

            {% endif %}

        </section>

        <div class="grid">

            <div class="stat">
                <strong>📚</strong>
                Academic Resources
            </div>

            <div class="stat">
                <strong>📄</strong>
                PDF Documents
            </div>

            <div class="stat">
                <strong>🔎</strong>
                Search Resources
            </div>

            <div class="stat">
                <strong>⬇</strong>
                Document Downloads
            </div>

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

        if not name or not email or not password:

            flash(
                "All fields are required.",
                "danger"
            )

            return redirect(
                url_for("register")
            )

        if len(password) < 6:

            flash(
                "Password must contain at least 6 characters.",
                "danger"
            )

            return redirect(
                url_for("register")
            )

        result, error = auth_register(
            email,
            password
        )

        if error:

            flash(
                "Registration failed: "
                + error[:250],
                "danger"
            )

            return redirect(
                url_for("register")
            )

        user = result.get(
            "user"
        )

        if not user:

            flash(
                "Account could not be created.",
                "danger"
            )

            return redirect(
                url_for("register")
            )

        uid = user.get(
            "id"
        )

        try:

            supabase_insert(
                "profiles",
                {
                    "id": uid,
                    "name": name,
                    "email": email,
                    "role": "student"
                }
            )

        except Exception as exc:

            logger.error(
                "Profile creation failed: %s",
                exc
            )

            flash(
                "Account created, but profile setup failed.",
                "warning"
            )

            return redirect(
                url_for("login")
            )

        flash(
            "Account created successfully. Please log in.",
            "success"
        )

        return redirect(
            url_for("login")
        )

    return page(
        "Create Account",
        """
        <div class="card">

            <h2>Create KOJA Account</h2>

            <form method="POST">

                <label>Name</label>

                <input
                    name="name"
                    required
                    autocomplete="name"
                >

                <label>Email</label>

                <input
                    type="email"
                    name="email"
                    required
                    autocomplete="email"
                >

                <label>Password</label>

                <input
                    type="password"
                    name="password"
                    minlength="6"
                    required
                    autocomplete="new-password"
                >

                <button>
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

        result = auth_login(
            email,
            password
        )

        if not result:

            flash(
                "Invalid email or password.",
                "danger"
            )

            return redirect(
                url_for("login")
            )

        user = result.get(
            "user"
        )

        if not user:

            flash(
                "Login failed.",
                "danger"
            )

            return redirect(
                url_for("login")
            )

        session.clear()

        session["user_id"] = user.get(
            "id"
        )

        session["email"] = email

        session["access_token"] = result.get(
            "access_token"
        )

        flash(
            "Welcome to KOJA AFRICA.",
            "success"
        )

        return redirect(
            url_for("documents")
        )

    return page(
        "Login",
        """
        <div class="card">

            <h2>Login</h2>

            <form method="POST">

                <label>Email</label>

                <input
                    type="email"
                    name="email"
                    required
                    autocomplete="email"
                >

                <label>Password</label>

                <input
                    type="password"
                    name="password"
                    required
                    autocomplete="current-password"
                >

                <button>
                    Login
                </button>

            </form>

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
    ).strip()

    document_type = request.args.get(
        "type",
        ""
    ).strip()

    params = {
        "select":
            "*",
        "is_active":
            "eq.true",
        "order":
            "created_at.desc"
    }

    if search:

        safe_search = (
            search
            .replace(",", " ")
            .replace("(", " ")
            .replace(")", " ")
        )

        params["or"] = (
            f"(title.ilike.*{safe_search}*,"
            f"description.ilike.*{safe_search}*,"
            f"subject.ilike.*{safe_search}*,"
            f"course.ilike.*{safe_search}*,"
            f"class_level.ilike.*{safe_search}*)"
        )

    if document_type:

        params["document_type"] = (
            f"eq.{document_type}"
        )

    try:

        docs = supabase_get(
            "documents",
            params
        )

    except Exception as exc:

        logger.error(
            "Document listing failed: %s",
            exc
        )

        docs = []

        flash(
            "Could not load documents.",
            "danger"
        )

    return page(
        "Documents",
        """
        <div class="card">

            <h2>Document Library</h2>

            <form method="GET">

                <input
                    name="search"
                    value="{{ search }}"
                    placeholder="Search documents..."
                >

                <select name="type">

                    <option value="">
                        All document types
                    </option>

                    {% for t in types %}

                    <option
                        value="{{ t }}"
                        {% if document_type == t %}
                        selected
                        {% endif %}
                    >
                        {{ t.replace('_',' ').title() }}
                    </option>

                    {% endfor %}

                </select>

                <button>
                    Search
                </button>

            </form>

        </div>


        <div class="grid">

        {% for d in docs %}

            <div class="card document">

                <span class="badge">
                    {{ d.document_type.replace('_',' ').title() }}
                </span>

                <h3>
                    {{ d.title }}
                </h3>

                {% if d.description %}

                <p class="muted">
                    {{ d.description }}
                </p>

                {% endif %}

                {% if d.subject %}

                <p>
                    <strong>Subject:</strong>
                    {{ d.subject }}
                </p>

                {% endif %}

                {% if d.course %}

                <p>
                    <strong>Course:</strong>
                    {{ d.course }}
                </p>

                {% endif %}

                {% if d.class_level %}

                <p>
                    <strong>Class:</strong>
                    {{ d.class_level }}
                </p>

                {% endif %}

                <p class="muted">
                    {{ d.file_name }}
                </p>

                <p class="muted">
                    Views: {{ d.view_count }}
                    |
                    Downloads: {{ d.download_count }}
                </p>

                <a
                    class="btn"
                    href="{{ url_for(
                        'view_document',
                        document_id=d.id
                    ) }}"
                >
                    View
                </a>

                <a
                    class="btn btn-green"
                    href="{{ url_for(
                        'download_document',
                        document_id=d.id
                    ) }}"
                >
                    Download
                </a>

            </div>

        {% else %}

            <div class="card">

                <h3>
                    No documents found.
                </h3>

                <p>
                    Try another search.
                </p>

            </div>

        {% endfor %}

        </div>
        """,
        docs=docs,
        search=search,
        document_type=document_type,
        types=[
            "academic",
            "assignment",
            "notes",
            "past_paper",
            "report",
            "answer",
            "announcement",
            "other"
        ]
    )


# ============================================================
# GET SINGLE DOCUMENT
# ============================================================

def get_document(
    document_id
):

    rows = supabase_get(
        "documents",
        {
            "select":
                "*",
            "id":
                f"eq.{document_id}",
            "limit":
                "1"
        }
    )

    if not rows:

        return None

    return rows[0]


# ============================================================
# VIEW DOCUMENT
# ============================================================

@app.route(
    "/documents/<document_id>"
)
@login_required
def view_document(
    document_id
):

    document = get_document(
        document_id
    )

    if not document:

        abort(404)

    if not document.get(
        "is_active"
    ):

        abort(404)

    # Increase view count

    new_count = (
        int(
            document.get(
                "view_count",
                0
            )
        )
        + 1
    )

    try:

        supabase_update(
            "documents",
            {
                "id":
                    f"eq.{document_id}"
            },
            {
                "view_count":
                    new_count
            }
        )

    except Exception as exc:

        logger.error(
            "View count update failed: %s",
            exc
        )

    record_document_action(
        document_id,
        "viewed"
    )

    return page(
        "View Document",
        """
        <div class="card">

            <span class="badge">
                {{ document.document_type
                   .replace('_',' ')
                   .title() }}
            </span>

            <h2>
                {{ document.title }}
            </h2>

            {% if document.description %}

            <p>
                {{ document.description }}
            </p>

            {% endif %}

            <hr>

            <p>
                <strong>File:</strong>
                {{ document.file_name }}
            </p>

            {% if document.subject %}

            <p>
                <strong>Subject:</strong>
                {{ document.subject }}
            </p>

            {% endif %}

            {% if document.course %}

            <p>
                <strong>Course:</strong>
                {{ document.course }}
            </p>

            {% endif %}

            <div style="margin-top:20px">

                <a
                    class="btn"
                    href="{{ url_for(
                        'download_document',
                        document_id=document.id
                    ) }}"
                >
                    Download Document
                </a>

                <a
                    class="btn btn-dark"
                    href="{{ url_for('documents') }}"
                >
                    Back
                </a>

            </div>

        </div>
        """,
        document=document
    )


# ============================================================
# DOWNLOAD DOCUMENT
# ============================================================

@app.route(
    "/documents/<document_id>/download"
)
@login_required
def download_document(
    document_id
):

    document = get_document(
        document_id
    )

    if not document:

        abort(404)

    if not document.get(
        "is_active"
    ):

        abort(404)

    path = document.get(
        "file_path"
    )

    if not path:

        flash(
            "Document file is missing.",
            "danger"
        )

        return redirect(
            url_for("documents")
        )

    try:

        data = download_storage(
            path
        )

    except Exception as exc:

        logger.error(
            "Download failed: %s",
            exc
        )

        flash(
            "Could not download the document.",
            "danger"
        )

        return redirect(
            url_for(
                "view_document",
                document_id=document_id
            )
        )

    # Increase download count

    new_count = (
        int(
            document.get(
                "download_count",
                0
            )
        )
        + 1
    )

    try:

        supabase_update(
            "documents",
            {
                "id":
                    f"eq.{document_id}"
            },
            {
                "download_count":
                    new_count
            }
        )

    except Exception as exc:

        logger.error(
            "Download count update failed: %s",
            exc
        )

    record_document_action(
        document_id,
        "downloaded"
    )

    filename = secure_filename(
        document.get(
            "file_name",
            "document.pdf"
        )
    )

    return send_file(
        io.BytesIO(data),
        mimetype=document.get(
            "mime_type",
            "application/pdf"
        ),
        as_attachment=True,
        download_name=filename
    )


# ============================================================
# ADMIN DASHBOARD
# ============================================================

@app.route("/admin")
@admin_required
def admin_dashboard():

    try:

        documents_data = supabase_get(
            "documents",
            {
                "select":
                    "*",
                "order":
                    "created_at.desc"
            }
        )

        records = supabase_get(
            "document_records",
            {
                "select":
                    "*",
                "order":
                    "created_at.desc",
                "limit":
                    "100"
            }
        )

    except Exception as exc:

        logger.error(
            "Admin dashboard failed: %s",
            exc
        )

        documents_data = []
        records = []

        flash(
            "Could not load admin data.",
            "danger"
        )

    total = len(
        documents_data
    )

    active = sum(
        1
        for d in documents_data
        if d.get("is_active")
    )

    public = sum(
        1
        for d in documents_data
        if d.get("is_public")
    )

    downloads = sum(
        int(
            d.get(
                "download_count",
                0
            )
        )
        for d in documents_data
    )

    views = sum(
        int(
            d.get(
                "view_count",
                0
            )
        )
        for d in documents_data
    )

    return page(
        "Admin Dashboard",
        """
        <section class="hero">

            <h1>
                Admin Dashboard
            </h1>

            <p>
                Manage KOJA AFRICA documents
                and monitor document activity.
            </p>

        </section>


        <div class="grid">

            <div class="stat">
                <strong>
                    {{ total }}
                </strong>
                Total Documents
            </div>

            <div class="stat">
                <strong>
                    {{ active }}
                </strong>
                Active Documents
            </div>

            <div class="stat">
                <strong>
                    {{ public }}
                </strong>
                Public Documents
            </div>

            <div class="stat">
                <strong>
                    {{ views }}
                </strong>
                Total Views
            </div>

            <div class="stat">
                <strong>
                    {{ downloads }}
                </strong>
                Total Downloads
            </div>

        </div>


        <div class="card">

            <h2>
                Upload Document
            </h2>

            <a
                class="btn btn-green"
                href="{{ url_for(
                    'admin_upload'
                ) }}"
            >
                + Upload Document
            </a>

        </div>


        <div class="card">

            <h2>
                Document Management
            </h2>

            <table>

                <thead>

                <tr>

                    <th>Title</th>
                    <th>Type</th>
                    <th>Subject</th>
                    <th>Views</th>
                    <th>Downloads</th>
                    <th>Status</th>
                    <th>Actions</th>

                </tr>

                </thead>

                <tbody>

                {% for d in docs %}

                <tr>

                    <td>
                        {{ d.title }}
                    </td>

                    <td>
                        {{ d.document_type }}
                    </td>

                    <td>
                        {{ d.subject or '-' }}
                    </td>

                    <td>
                        {{ d.view_count }}
                    </td>

                    <td>
                        {{ d.download_count }}
                    </td>

                    <td>

                        {% if d.is_active %}

                        <span class="badge">
                            Active
                        </span>

                        {% else %}

                        <span class="badge">
                            Inactive
                        </span>

                        {% endif %}

                    </td>

                    <td>

                        <a
                            class="btn"
                            href="{{ url_for(
                                'view_document',
                                document_id=d.id
                            ) }}"
                        >
                            View
                        </a>

                        <a
                            class="btn btn-red"
                            href="{{ url_for(
                                'admin_delete_document',
                                document_id=d.id
                            ) }}"
                            onclick="return confirm(
                                'Deactivate this document?'
                            )"
                        >
                            Deactivate
                        </a>

                    </td>

                </tr>

                {% endfor %}

                </tbody>

            </table>

        </div>


        <div class="card">

            <h2>
                Recent Activity
            </h2>

            <table>

                <thead>

                <tr>

                    <th>Action</th>
                    <th>Document ID</th>
                    <th>User ID</th>
                    <th>Date</th>

                </tr>

                </thead>

                <tbody>

                {% for r in records %}

                <tr>

                    <td>
                        <span class="badge">
                            {{ r.action }}
                        </span>
                    </td>

                    <td>
                        {{ r.document_id or 'Deleted document' }}
                    </td>

                    <td>
                        {{ r.user_id or '-' }}
                    </td>

                    <td>
                        {{ r.created_at }}
                    </td>

                </tr>

                {% endfor %}

                </tbody>

            </table>

        </div>
        """,
        docs=documents_data,
        records=records,
        total=total,
        active=active,
        public=public,
        views=views,
        downloads=downloads
    )


# ============================================================
# ADMIN UPLOAD
# ============================================================

@app.route(
    "/admin/documents/upload",
    methods=["GET", "POST"]
)
@admin_required
def admin_upload():

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
        ).strip()

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

        uploaded_file = request.files.get(
            "file"
        )

        allowed_types = {
            "academic",
            "assignment",
            "notes",
            "past_paper",
            "report",
            "answer",
            "announcement",
            "other"
        }

        if not title:

            flash(
                "Document title is required.",
                "danger"
            )

            return redirect(
                url_for("admin_upload")
            )

        if document_type not in allowed_types:

            flash(
                "Invalid document type.",
                "danger"
            )

            return redirect(
                url_for("admin_upload")
            )

        if not uploaded_file:

            flash(
                "Please select a file.",
                "danger"
            )

            return redirect(
                url_for("admin_upload")
            )

        original_name = (
            uploaded_file.filename
            or ""
        )

        if not original_name:

            flash(
                "Invalid filename.",
                "danger"
            )

            return redirect(
                url_for("admin_upload")
            )

        filename = secure_filename(
            original_name
        )

        extension = (
            os.path.splitext(
                filename
            )[1]
            .lower()
        )

        allowed_extensions = {
            ".pdf"
        }

        if extension not in allowed_extensions:

            flash(
                "Only PDF documents are currently allowed.",
                "danger"
            )

            return redirect(
                url_for("admin_upload")
            )

        # Generate unique storage path

        storage_path = (
            datetime.now(
                timezone.utc
            ).strftime(
                "%Y/%m"
            )
            + "/"
            + str(uuid.uuid4())
            + ".pdf"
        )

        try:

            uploaded_file.stream.seek(0)

            upload_storage(
                uploaded_file,
                storage_path
            )

            file_size = (
                uploaded_file.content_length
                or 0
            )

            # Save metadata

            rows = supabase_insert(
                "documents",
                {
                    "title":
                        title,

                    "description":
                        description or None,

                    "document_type":
                        document_type,

                    "subject":
                        subject or None,

                    "course":
                        course or None,

                    "class_level":
                        class_level or None,

                    "file_name":
                        filename,

                    "file_path":
                        storage_path,

                    "file_url":
                        None,

                    "file_size":
                        file_size,

                    "mime_type":
                        "application/pdf",

                    "uploaded_by":
                        current_user_id(),

                    "is_public":
                        is_public,

                    "is_active":
                        True
                }
            )

            document_id = None

            if rows:

                document_id = rows[0].get(
                    "id"
                )

            if document_id:

                record_document_action(
                    document_id,
                    "uploaded"
                )

            flash(
                "Document uploaded successfully.",
                "success"
            )

            return redirect(
                url_for(
                    "admin_dashboard"
                )
            )

        except Exception as exc:

            logger.exception(
                "Document upload failed"
            )

            flash(
                "Upload failed: "
                + str(exc)[:300],
                "danger"
            )

            return redirect(
                url_for("admin_upload")
            )

    return page(
        "Upload Document",
        """
        <div class="card">

            <h2>
                Upload Academic Document
            </h2>

            <form
                method="POST"
                enctype="multipart/form-data"
            >

                <label>
                    Document Title
                </label>

                <input
                    name="title"
                    placeholder="e.g. Grade 12 Biology Notes"
                    required
                >

                <label>
                    Description
                </label>

                <textarea
                    name="description"
                    placeholder="Describe the document..."
                ></textarea>

                <label>
                    Document Type
                </label>

                <select
                    name="document_type"
                    required
                >

                    {% for t in types %}

                    <option value="{{ t }}">
                        {{ t.replace('_',' ').title() }}
                    </option>

                    {% endfor %}

                </select>

                <label>
                    Subject
                </label>

                <input
                    name="subject"
                    placeholder="Biology"
                >

                <label>
                    Course
                </label>

                <input
                    name="course"
                    placeholder="Biology 12"
                >

                <label>
                    Class Level
                </label>

                <input
                    name="class_level"
                    placeholder="Grade 12"
                >

                <label>
                    PDF File
                </label>

                <input
                    type="file"
                    name="file"
                    accept="application/pdf,.pdf"
                    required
                >

                <label>

                    <input
                        type="checkbox"
                        name="is_public"
                        style="width:auto"
                    >

                    Make this document public

                </label>

                <br><br>

                <button>
                    Upload Document
                </button>

                <a
                    class="btn btn-dark"
                    href="{{ url_for(
                        'admin_dashboard'
                    ) }}"
                >
                    Cancel
                </a>

            </form>

        </div>
        """,
        types=[
            "academic",
            "assignment",
            "notes",
            "past_paper",
            "report",
            "answer",
            "announcement",
            "other"
        ]
    )


# ============================================================
# ADMIN DEACTIVATE DOCUMENT
# ============================================================

@app.route(
    "/admin/documents/<document_id>/delete"
)
@admin_required
def admin_delete_document(
    document_id
):

    document = get_document(
        document_id
    )

    if not document:

        flash(
            "Document not found.",
            "danger"
        )

        return redirect(
            url_for("admin_dashboard")
        )

    try:

        # Preserve document record.
        # We deactivate instead of physically
        # deleting the database row.

        supabase_update(
            "documents",
            {
                "id":
                    f"eq.{document_id}"
            },
            {
                "is_active":
                    False
            }
        )

        record_document_action(
            document_id,
            "deleted"
        )

        flash(
            "Document deactivated.",
            "success"
        )

    except Exception as exc:

        logger.error(
            "Document deactivation failed: %s",
            exc
        )

        flash(
            "Could not deactivate document.",
            "danger"
        )

    return redirect(
        url_for(
            "admin_dashboard"
        )
    )


# ============================================================
# ADMIN RESTORE DOCUMENT
# ============================================================

@app.route(
    "/admin/documents/<document_id>/restore"
)
@admin_required
def admin_restore_document(
    document_id
):

    try:

        supabase_update(
            "documents",
            {
                "id":
                    f"eq.{document_id}"
            },
            {
                "is_active":
                    True
            }
        )

        record_document_action(
            document_id,
            "updated"
        )

        flash(
            "Document restored.",
            "success"
        )

    except Exception as exc:

        logger.error(
            "Restore failed: %s",
            exc
        )

        flash(
            "Could not restore document.",
            "danger"
        )

    return redirect(
        url_for(
            "admin_dashboard"
        )
    )


# ============================================================
# ADMIN PROFILE
# ============================================================

@app.route("/admin/profile")
@admin_required
def admin_profile():

    profile = current_user()

    return page(
        "Admin Profile",
        """
        <div class="card">

            <h2>
                Administrator
            </h2>

            <p>
                <strong>Name:</strong>
                {{ profile.name }}
            </p>

            <p>
                <strong>Email:</strong>
                {{ profile.email }}
            </p>

            <p>
                <strong>Role:</strong>
                {{ profile.role }}
            </p>

            <p>
                <strong>User ID:</strong>
                {{ profile.id }}
            </p>

        </div>
        """,
        profile=profile
    )


# ============================================================
# PDF GENERATOR
# ============================================================

def build_answer_pdf(
    subject,
    student_name,
    question,
    answer
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

    title_style.alignment = TA_CENTER

    heading = styles["Heading2"]

    body = styles["BodyText"]

    story = []

    story.append(
        Paragraph(
            "KOJA AFRICA",
            title_style
        )
    )

    story.append(
        Spacer(1, 15)
    )

    table_data = [
        ["Subject", escape(subject or "")],
        ["Student", escape(student_name or "")],
    ]

    table = Table(
        table_data,
        colWidths=[
            100,
            350
        ]
    )

    table.setStyle(
        TableStyle([
            (
                "GRID",
                (0,0),
                (-1,-1),
                0.5,
                colors.grey
            ),
            (
                "BACKGROUND",
                (0,0),
                (0,-1),
                colors.lightgrey
            ),
            (
                "VALIGN",
                (0,0),
                (-1,-1),
                "TOP"
            ),
        ])
    )

    story.append(
        table
    )

    story.append(
        Spacer(1, 20)
    )

    story.append(
        Paragraph(
            "Question",
            heading
        )
    )

    story.append(
        Paragraph(
            escape(
                question or ""
            ).replace(
                "\n",
                "<br/>"
            ),
            body
        )
    )

    story.append(
        Spacer(1, 20)
    )

    story.append(
        Paragraph(
            "Answer",
            heading
        )
    )

    story.append(
        Paragraph(
            escape(
                answer or ""
            ).replace(
                "\n",
                "<br/>"
            ),
            body
        )
    )

    story.append(
        Spacer(1, 30)
    )

    story.append(
        Paragraph(
            "Generated by KOJA AFRICA",
            body
        )
    )

    document.build(
        story
    )

    buffer.seek(0)

    return buffer


# ============================================================
# PDF TEST ROUTE
# ============================================================

@app.route(
    "/admin/test-pdf"
)
@admin_required
def test_pdf():

    pdf = build_answer_pdf(
        "Biology",
        "KOJA Student",
        "Define photosynthesis.",
        (
            "Photosynthesis is the process "
            "by which green plants use light "
            "energy to manufacture glucose "
            "from carbon dioxide and water."
        )
    )

    return send_file(
        pdf,
        mimetype="application/pdf",
        as_attachment=True,
        download_name="koja-answer.pdf"
    )


# ============================================================
# HEALTH CHECK
# ============================================================

@app.route("/health")
def health():

    if not SUPABASE_URL:

        return {
            "status":
                "error",
            "message":
                "SUPABASE_URL is missing"
        }, 500

    if not SUPABASE_SERVICE_KEY:

        return {
            "status":
                "error",
            "message":
                "SUPABASE_SERVICE_KEY is missing"
        }, 500

    try:

        supabase_get(
            "documents",
            {
                "select":
                    "id",
                "limit":
                    "1"
            }
        )

        return {
            "status":
                "ok",
            "database":
                "connected",
            "storage_bucket":
                STORAGE_BUCKET
        }

    except Exception as exc:

        return {
            "status":
                "error",
            "database":
                "connection failed",
            "message":
                str(exc)[:300]
        }, 500


# ============================================================
# ERROR HANDLERS
# ============================================================

@app.errorhandler(404)
def not_found(error):

    return page(
        "Not Found",
        """
        <div class="card">

            <h2>
                Page not found
            </h2>

            <p>
                The requested resource does not exist.
            </p>

            <a
                class="btn"
                href="{{ url_for('home') }}"
            >
                Return Home
            </a>

        </div>
        """
    ), 404


@app.errorhandler(413)
def file_too_large(error):

    flash(
        "File is too large. Maximum size is 10 MB.",
        "danger"
    )

    return redirect(
        url_for("admin_upload")
    )


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    if not SUPABASE_URL:

        print(
            "ERROR: SUPABASE_URL is not configured."
        )

    elif not SUPABASE_SERVICE_KEY:

        print(
            "ERROR: SUPABASE_SERVICE_KEY is not configured."
        )

    else:

        print(
            "======================================"
        )

        print(
            "KOJA AFRICA"
        )

        print(
            "Document Portal"
        )

        print(
            "======================================"
        )

        print(
            "Supabase:",
            SUPABASE_URL
        )

        print(
            "Storage:",
            STORAGE_BUCKET
        )

        print(
            "Admin:",
            ADMIN_UUID
        )

        print(
            "Local:"
        )

        print(
            "http://127.0.0.1:5000"
        )

        print(
            "======================================"
        )

    app.run(
        host="0.0.0.0",
        port=int(
            os.getenv(
                "PORT",
                "5000"
            )
        ),
        debug=False
    )

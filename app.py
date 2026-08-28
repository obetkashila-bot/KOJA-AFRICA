import os
import io
import json
import uuid
import secrets
import logging

from datetime import datetime, timezone
from functools import wraps
from urllib.parse import quote

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

from werkzeug.security import (
    generate_password_hash,
    check_password_hash,
)


# ============================================================
# CONFIGURATION
# ============================================================

load_dotenv()

app = Flask(__name__)

app.secret_key = os.getenv(
    "SECRET_KEY",
    secrets.token_hex(32)
)

app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024

logging.basicConfig(level=logging.INFO)

SUPABASE_URL = os.getenv(
    "SUPABASE_URL",
    ""
).rstrip("/")

SUPABASE_SERVICE_KEY = os.getenv(
    "SUPABASE_SERVICE_KEY",
    ""
)

ADMIN_USERNAME = os.getenv(
    "ADMIN_USERNAME",
    "admin"
)

ADMIN_PASSWORD = os.getenv(
    "ADMIN_PASSWORD",
    ""
)

STORAGE_BUCKET = os.getenv(
    "SUPABASE_STORAGE_BUCKET",
    "koja-assignments"
)

APP_NAME = "KOJA AFRICA"

APP_TAGLINE = (
    "Your Request • KOJA Handles It"
)

STATUS_NEW = "New"
STATUS_PROCESSING = "Processing"
STATUS_COMPLETED = "Completed"

ALLOWED_EXTENSIONS = {
    "pdf",
    "doc",
    "docx",
    "txt",
    "jpg",
    "jpeg",
    "png",
    "webp",
    "xls",
    "xlsx",
    "ppt",
    "pptx",
    "zip",
}


# ============================================================
# PUBLIC KOJA SERVICES
# ============================================================

PUBLIC_SERVICES = [
    "Assignments",
    "University Applications",
    "Result Verification & Certification",
    "Farmer Registration",
    "TPN Centre",
    "Higher Education Materials",
]

SERVICE_DESCRIPTIONS = {
    "Assignments":
        "Submit academic assignments, questions, "
        "supporting documents and related academic work.",

    "University Applications":
        "Get assistance with university and higher "
        "education application requests and documents.",

    "Result Verification & Certification":
        "Submit academic result verification, "
        "certification and related document requests.",

    "Farmer Registration":
        "Submit farmer registration requests "
        "and supporting information.",

    "TPN Centre":
        "Submit TPN-related requests together with "
        "your personal and address information.",

    "Higher Education Materials":
        "Request higher education materials, "
        "academic documents and related resources.",
}


# ============================================================
# UNIVERSITY SERVICES
# ============================================================

UNIVERSITY_SERVICES = {
    "University Applications",
    "Result Verification & Certification",
    "Higher Education Materials",
}


# ============================================================
# HELPERS
# ============================================================

def configuration_ok():
    return bool(
        SUPABASE_URL and
        SUPABASE_SERVICE_KEY
    )


def require_configuration():
    if not configuration_ok():
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_SERVICE_KEY "
            "are not configured."
        )


def now_iso():
    return datetime.now(
        timezone.utc
    ).isoformat()


def clean(value, maximum=5000):
    return (
        value or ""
    ).strip()[:maximum]


def allowed_file(filename):
    if not filename:
        return False

    if "." not in filename:
        return False

    extension = (
        filename.rsplit(".", 1)[1].lower()
    )

    return extension in ALLOWED_EXTENSIONS


def safe_filename(filename):
    filename = os.path.basename(
        filename or "file"
    )

    filename = filename.replace(
        "\x00",
        ""
    )

    return filename[:180]


def client_status_label(status):
    if status == STATUS_NEW:
        return "Request Received"

    if status == STATUS_PROCESSING:
        return "KOJA Is Working on It"

    if status == STATUS_COMPLETED:
        return "Ready — Completed"

    return status or "Request Received"


def status_class(status):
    if status == STATUS_COMPLETED:
        return "completed"

    if status == STATUS_PROCESSING:
        return "processing"

    return "new"


def generate_csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)

    return session["csrf_token"]


def validate_csrf():
    token = request.form.get("csrf_token", "")

    saved = session.get(
        "csrf_token",
        ""
    )

    if not token or not saved:
        abort(400)

    if not secrets.compare_digest(
        token,
        saved
    ):
        abort(400)


app.jinja_env.globals["csrf_token"] = generate_csrf_token
app.jinja_env.globals["client_status_label"] = client_status_label
app.jinja_env.globals["status_class"] = status_class


# ============================================================
# SUPABASE REST API
# ============================================================

def supabase_headers(prefer=None):
    require_configuration()

    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization":
            "Bearer " + SUPABASE_SERVICE_KEY,
        "Content-Type": "application/json",
    }

    if prefer:
        headers["Prefer"] = prefer

    return headers


def supabase_request(
    method,
    path,
    **kwargs
):
    require_configuration()

    url = (
        SUPABASE_URL
        + "/rest/v1/"
        + path
    )

    supplied_headers = kwargs.pop(
        "headers",
        {}
    )

    headers = supabase_headers()

    headers.update(
        supplied_headers
    )

    response = requests.request(
        method,
        url,
        headers=headers,
        timeout=30,
        **kwargs
    )

    if not response.ok:
        logging.error(
            "Supabase request failed: "
            "%s %s %s %s",
            method,
            path,
            response.status_code,
            response.text[:2000]
        )

        raise RuntimeError(
            "Supabase request failed "
            f"({response.status_code}): "
            f"{response.text[:700]}"
        )

    if not response.text:
        return None

    try:
        return response.json()
    except Exception:
        return response.text


def db_select(
    table,
    select="*",
    filters=None,
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

    return supabase_request(
        "GET",
        table,
        params=params
    )


def db_insert(
    table,
    data,
    returning=True
):
    prefer = (
        "return=representation"
        if returning
        else
        "return=minimal"
    )

    return supabase_request(
        "POST",
        table,
        headers={
            "Prefer": prefer
        },
        json=data
    )


def db_update(
    table,
    filters,
    data,
    returning=True
):
    prefer = (
        "return=representation"
        if returning
        else
        "return=minimal"
    )

    return supabase_request(
        "PATCH",
        table,
        headers={
            "Prefer": prefer
        },
        params=dict(filters),
        json=data
    )


# ============================================================
# SUPABASE STORAGE
# ============================================================

def storage_upload(
    file_storage,
    folder="supporting"
):
    require_configuration()

    original_name = safe_filename(
        file_storage.filename
    )

    extension = ""

    if "." in original_name:
        extension = (
            original_name
            .rsplit(".", 1)[1]
            .lower()
        )

    unique_name = (
        uuid.uuid4().hex
        +
        (
            "." + extension
            if extension
            else ""
        )
    )

    storage_path = (
        folder
        + "/"
        + unique_name
    )

    content_type = (
        file_storage.mimetype
        or
        "application/octet-stream"
    )

    url = (
        SUPABASE_URL
        + "/storage/v1/object/"
        + quote(
            STORAGE_BUCKET,
            safe=""
        )
        + "/"
        + quote(
            storage_path,
            safe="/"
        )
    )

    headers = {
        "Authorization":
            "Bearer " + SUPABASE_SERVICE_KEY,

        "apikey":
            SUPABASE_SERVICE_KEY,

        "Content-Type":
            content_type,

        "x-upsert":
            "false",
    }

    file_storage.stream.seek(0)

    response = requests.post(
        url,
        headers=headers,
        data=file_storage.stream,
        timeout=90
    )

    if not response.ok:
        raise RuntimeError(
            "File upload failed "
            f"({response.status_code}): "
            f"{response.text[:700]}"
        )

    return {
        "path":
            storage_path,

        "file_name":
            original_name,

        "content_type":
            content_type,

        "size":
            request.content_length or 0,
    }


def storage_download(path):
    require_configuration()

    url = (
        SUPABASE_URL
        + "/storage/v1/object/"
        + quote(
            STORAGE_BUCKET,
            safe=""
        )
        + "/"
        + quote(
            path,
            safe="/"
        )
    )

    headers = {
        "Authorization":
            "Bearer " + SUPABASE_SERVICE_KEY,

        "apikey":
            SUPABASE_SERVICE_KEY,
    }

    response = requests.get(
        url,
        headers=headers,
        timeout=90
    )

    if not response.ok:
        raise RuntimeError(
            "Storage download failed "
            f"({response.status_code}): "
            f"{response.text[:700]}"
        )

    return response


# ============================================================
# REQUEST NUMBER
# ============================================================

def generate_request_number():

    date_part = datetime.now(
        timezone.utc
    ).strftime("%Y%m%d")

    random_part = secrets.token_hex(
        4
    ).upper()

    return (
        "KOJA-"
        + date_part
        + "-"
        + random_part
    )


def create_unique_request_number():

    for _ in range(15):

        number = generate_request_number()

        existing = db_select(
            "koja_service_requests",
            select="id",
            filters={
                "request_number":
                    "eq." + number
            },
            limit=1
        )

        if not existing:
            return number

    raise RuntimeError(
        "Could not generate a unique "
        "request number."
    )


# ============================================================
# AUTH DECORATORS
# ============================================================

def client_login_required(function):

    @wraps(function)
    def wrapper(*args, **kwargs):

        if not session.get("client_id"):

            flash(
                "Please log in or create "
                "a KOJA account first."
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

        if not session.get(
            "admin_logged_in"
        ):

            flash(
                "Administrator login required."
            )

            return redirect(
                url_for("admin_login")
            )

        return function(
            *args,
            **kwargs
        )

    return wrapper


# ============================================================
# HTML / CSS
# ============================================================

BASE_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">

<meta
    name="viewport"
    content="width=device-width,
             initial-scale=1.0"
>

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

    background:
        #f4f7fb;

    color:
        #172033;
}

.nav {
    background:
        #ffffff;

    border-bottom:
        1px solid #e5e7eb;

    padding:
        14px 5%;

    display:
        flex;

    justify-content:
        space-between;

    align-items:
        center;

    gap:
        15px;

    position:
        sticky;

    top: 0;

    z-index: 10;
}

.logo {
    font-size:
        22px;

    font-weight:
        800;

    color:
        #173f8a;
}

.navlinks {
    display:
        flex;

    flex-wrap:
        wrap;

    gap:
        7px;

    justify-content:
        flex-end;
}

.navlinks a {
    text-decoration:
        none;

    color:
        #24324a;

    padding:
        8px 11px;

    border-radius:
        8px;

    font-size:
        14px;
}

.navlinks a:hover {
    background:
        #eef3ff;
}

.container {
    width:
        min(1100px, 92%);

    margin:
        30px auto;
}

.card {
    background:
        white;

    border-radius:
        16px;

    padding:
        24px;

    margin-bottom:
        20px;

    box-shadow:
        0 6px 24px
        rgba(20, 35, 70, 0.07);
}

.hero {
    text-align:
        center;

    padding:
        45px 25px;
}

.hero h1 {
    margin:
        0 0 10px;

    font-size:
        clamp(30px, 7vw, 54px);

    color:
        #173f8a;
}

.hero p {
    font-size:
        17px;

    line-height:
        1.7;

    color:
        #586579;
}

.grid {
    display:
        grid;

    grid-template-columns:
        repeat(auto-fit, minmax(230px, 1fr));

    gap:
        18px;
}

.service-card {
    background:
        white;

    padding:
        22px;

    border-radius:
        15px;

    box-shadow:
        0 5px 20px
        rgba(20, 35, 70, 0.07);

    border:
        1px solid #edf0f5;
}

.service-card h3 {
    margin-top:
        0;

    color:
        #173f8a;
}

.service-card p {
    color:
        #596579;

    line-height:
        1.55;
}

input,
select,
textarea {
    width:
        100%;

    padding:
        12px 13px;

    border:
        1px solid #ccd3df;

    border-radius:
        9px;

    font-size:
        15px;

    margin-top:
        6px;

    margin-bottom:
        15px;

    background:
        #fff;
}

textarea {
    min-height:
        150px;

    resize:
        vertical;
}

label {
    font-weight:
        700;

    font-size:
        14px;
}

button,
.btn {
    display:
        inline-block;

    border:
        0;

    background:
        #173f8a;

    color:
        white;

    padding:
        11px 16px;

    border-radius:
        9px;

    cursor:
        pointer;

    text-decoration:
        none;

    font-weight:
        700;

    margin:
        4px;
}

.btn:hover,
button:hover {
    opacity:
        .9;
}

.btn.green,
button.green {
    background:
        #16834b;
}

.btn.warning,
button.warning {
    background:
        #c27600;
}

.btn.red,
button.red {
    background:
        #b42318;
}

.btn.light {
    background:
        #eef2f7;

    color:
        #24324a;
}

.alert {
    padding:
        13px 16px;

    background:
        #fff7df;

    border:
        1px solid #efd38a;

    border-radius:
        9px;

    margin-bottom:
        15px;
}

.stats {
    display:
        grid;

    grid-template-columns:
        repeat(auto-fit, minmax(160px, 1fr));

    gap:
        15px;
}

.stat {
    background:
        white;

    padding:
        20px;

    border-radius:
        13px;

    box-shadow:
        0 5px 18px
        rgba(20, 35, 70, .06);
}

.stat strong {
    font-size:
        30px;

    display:
        block;

    margin-top:
        5px;
}

.status {
    display:
        inline-block;

    padding:
        5px 9px;

    border-radius:
        20px;

    font-size:
        12px;

    font-weight:
        700;
}

.status.new {
    background:
        #eaf2ff;

    color:
        #174ea6;
}

.status.processing {
    background:
        #fff3d7;

    color:
        #8a5700;
}

.status.completed {
    background:
        #e6f7ed;

    color:
        #08743d;
}

table {
    width:
        100%;

    border-collapse:
        collapse;

    background:
        white;
}

th,
td {
    text-align:
        left;

    padding:
        12px;

    border-bottom:
        1px solid #edf0f4;

    vertical-align:
        top;
}

.footer {
    text-align:
        center;

    padding:
        35px 15px;

    color:
        #667085;

    font-size:
        13px;
}

.section-title {
    color:
        #173f8a;

    margin-top:
        25px;
}

.info-box {
    background:
        #f7f9fc;

    border-left:
        4px solid #173f8a;

    padding:
        14px;

    margin:
        15px 0;

    border-radius:
        8px;
}

@media(max-width:700px) {

    .nav {
        align-items:
            flex-start;

        flex-direction:
            column;
    }

    .navlinks {
        justify-content:
            flex-start;
    }

    .card {
        padding:
            17px;
    }

    th,
    td {
        font-size:
            13px;

        padding:
            8px;
    }
}

</style>
</head>

<body>

<nav class="nav">

<div class="logo">
    KOJA AFRICA
</div>

<div class="navlinks">

<a href="{{ url_for('home') }}">
    Home
</a>

{% if session.get("client_id") %}

<a href="{{ url_for('services') }}">
    KOJA Services
</a>

<a href="{{ url_for('dashboard') }}">
    Dashboard
</a>

<a href="{{ url_for('my_requests') }}">
    My Requests
</a>

<a href="{{ url_for('notifications') }}">
    Notifications
</a>

<a href="{{ url_for('profile') }}">
    Profile
</a>

<a href="{{ url_for('logout') }}">
    Logout
</a>

{% else %}

<a href="{{ url_for('login') }}">
    Client Login
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

<div class="alert">
    {{ message }}
</div>

{% endfor %}

{% endwith %}

{{ body|safe }}

</div>

<footer class="footer">

<strong>KOJA AFRICA</strong>

<br>

{{ tagline }}

<br><br>

Your Request → KOJA Handles It → You Receive the Result

</footer>

</body>
</html>
"""


def page(
    title,
    body_template,
    **context
):

    body = render_template_string(
        body_template,
        **context
    )

    return render_template_string(
        BASE_HTML,
        title=title,
        body=body,
        tagline=APP_TAGLINE
    )


# ============================================================
# HOME
# ============================================================

@app.route("/")
def home():

    body = """
<div class="card hero">

<h1>KOJA AFRICA</h1>

<h2>
Your Request • KOJA Handles It
</h2>

<p>
KOJA AFRICA is a request-processing platform.
Create your account or log in first, then choose
the KOJA service you need.
</p>

{% if session.get("client_id") %}

<a class="btn"
   href="{{ url_for('services') }}">
    View KOJA Services
</a>

{% else %}

<a class="btn"
   href="{{ url_for('register') }}">
    Create KOJA Account
</a>

<a class="btn light"
   href="{{ url_for('login') }}">
    Client Login
</a>

{% endif %}

</div>

<div class="card">

<h2>
How KOJA Works
</h2>

<div class="grid">

<div class="service-card">
<h3>1. Create Account</h3>
<p>
Create your KOJA client account using your
basic contact information.
</p>
</div>

<div class="service-card">
<h3>2. Choose a Service</h3>
<p>
After logging in, choose the KOJA service
you need.
</p>
</div>

<div class="service-card">
<h3>3. Send Your Request</h3>
<p>
Provide the information required for the
selected service and upload documents.
</p>
</div>

<div class="service-card">
<h3>4. Track It</h3>
<p>
KOJA processes your request and updates
you through your account.
</p>
</div>

</div>

</div>
"""

    return page(
        "KOJA AFRICA",
        body
    )


# ============================================================
# SERVICES
# ============================================================

@app.route("/services")
@client_login_required
def services():

    body = """
<div class="card">

<h1>KOJA Services</h1>

<p>
Welcome, <strong>
{{ session.get("client_name") }}
</strong>.
</p>

<p>
Choose the service you want KOJA to handle.
</p>

</div>

<div class="grid">

{% for service in services %}

<div class="service-card">

<h3>
{{ service }}
</h3>

<p>
{{ descriptions.get(
    service,
    "Submit a request to KOJA."
) }}
</p>

<a class="btn"
   href="{{ url_for(
       'service_start',
       service=service
   ) }}">
    Request This Service
</a>

</div>

{% endfor %}

</div>
"""

    try:

        database_services = db_select(
            "koja_services",
            select="name,active",
            filters={
                "active": "eq.true"
            },
            order="name.asc"
        )

        services_from_db = [
            x.get("name")
            for x in database_services
            if x.get("name")
        ]

        services_list = [
            x for x in PUBLIC_SERVICES
            if x in services_from_db
        ]

        if not services_list:
            services_list = PUBLIC_SERVICES

    except Exception:

        logging.exception(
            "Service table could not be loaded"
        )

        services_list = PUBLIC_SERVICES

    return page(
        "KOJA Services",
        body,
        services=services_list,
        descriptions=SERVICE_DESCRIPTIONS
    )


# ============================================================
# SERVICE START
# ============================================================

@app.route("/service/<path:service>")
@client_login_required
def service_start(service):

    service = clean(
        service,
        200
    )

    if service not in PUBLIC_SERVICES:
        abort(404)

    return redirect(
        url_for(
            "new_request",
            service=service
        )
    )


# ============================================================
# REGISTER
# ============================================================

@app.route(
    "/register",
    methods=["GET", "POST"]
)
def register():

    if session.get("client_id"):
        return redirect(
            url_for("services")
        )

    if request.method == "POST":

        validate_csrf()

        name = clean(
            request.form.get("name"),
            150
        )

        email = clean(
            request.form.get("email"),
            180
        ).lower()

        phone = clean(
            request.form.get("phone"),
            60
        )

        password = request.form.get(
            "password",
            ""
        )

        if not name:
            flash(
                "Full name is required."
            )

        elif not email:
            flash(
                "Email address is required."
            )

        elif not phone:
            flash(
                "Phone/contact is required."
            )

        elif len(password) < 6:
            flash(
                "Password must be at least "
                "6 characters."
            )

        else:

            try:

                existing = db_select(
                    "koja_clients",
                    select="id",
                    filters={
                        "email":
                            "eq." + email
                    },
                    limit=1
                )

                if existing:

                    flash(
                        "An account with "
                        "that email already exists."
                    )

                    return redirect(
                        url_for("login")
                    )

                result = db_insert(
                    "koja_clients",
                    {
                        "name":
                            name,

                        "email":
                            email,

                        "phone":
                            phone,

                        "password_hash":
                            generate_password_hash(
                                password
                            ),

                        "created_at":
                            now_iso(),

                        "updated_at":
                            now_iso(),
                    }
                )

                client = result[0]

                session.clear()

                session["client_id"] = (
                    client["id"]
                )

                session["client_name"] = (
                    client["name"]
                )

                session["client_email"] = (
                    client["email"]
                )

                session["csrf_token"] = (
                    secrets.token_urlsafe(32)
                )

                flash(
                    "Account created successfully. "
                    "Choose a KOJA service."
                )

                return redirect(
                    url_for("services")
                )

            except Exception as exc:

                logging.exception(
                    "Registration failed"
                )

                flash(
                    "Registration error: "
                    + str(exc)[:350]
                )

    body = """
<div class="card">

<h2>Create KOJA Client Account</h2>

<p>
Only your basic account information is required here.
University information is collected later when it is
needed for a particular service.
</p>

<form method="POST">

<input
    type="hidden"
    name="csrf_token"
    value="{{ csrf_token() }}"
>

<label>
Full Name *
</label>

<input
    name="name"
    required
    autocomplete="name"
>

<label>
Email Address *
</label>

<input
    type="email"
    name="email"
    required
    autocomplete="email"
>

<label>
Phone / Contact *
</label>

<input
    name="phone"
    required
    placeholder="e.g. 097xxxxxxx"
>

<label>
Password *
</label>

<input
    type="password"
    name="password"
    required
    minlength="6"
    autocomplete="new-password"
>

<button type="submit">
Create Account
</button>

</form>

<p>
Already have an account?
<a href="{{ url_for('login') }}">
Login
</a>
</p>

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

    if session.get("client_id"):
        return redirect(
            url_for("services")
        )

    if request.method == "POST":

        validate_csrf()

        email = clean(
            request.form.get("email"),
            180
        ).lower()

        password = request.form.get(
            "password",
            ""
        )

        try:

            clients = db_select(
                "koja_clients",
                select="*",
                filters={
                    "email":
                        "eq." + email
                },
                limit=1
            )

            if not clients:

                flash(
                    "Invalid email or password."
                )

                return redirect(
                    url_for("login")
                )

            client = clients[0]

            if not check_password_hash(
                client["password_hash"],
                password
            ):

                flash(
                    "Invalid email or password."
                )

                return redirect(
                    url_for("login")
                )

            session.clear()

            session["client_id"] = (
                client["id"]
            )

            session["client_name"] = (
                client["name"]
            )

            session["client_email"] = (
                client["email"]
            )

            session["csrf_token"] = (
                secrets.token_urlsafe(32)
            )

            flash(
                "Welcome back. "
                "Choose a KOJA service."
            )

            return redirect(
                url_for("services")
            )

        except Exception as exc:

            logging.exception(
                "Login failed"
            )

            flash(
                "Login error: "
                + str(exc)[:350]
            )

    body = """
<div class="card">

<h2>KOJA Client Login</h2>

<form method="POST">

<input
    type="hidden"
    name="csrf_token"
    value="{{ csrf_token() }}"
>

<label>
Email
</label>

<input
    type="email"
    name="email"
    required
    autocomplete="email"
>

<label>
Password
</label>

<input
    type="password"
    name="password"
    required
    autocomplete="current-password"
>

<button type="submit">
Login
</button>

</form>

<p>
No account?
<a href="{{ url_for('register') }}">
Create one
</a>
</p>

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

    flash(
        "You have been logged out."
    )

    return redirect(
        url_for("home")
    )


# ============================================================
# PROFILE
# ============================================================

@app.route(
    "/profile",
    methods=["GET", "POST"]
)
@client_login_required
def profile():

    rows = db_select(
        "koja_clients",
        select="*",
        filters={
            "id":
                "eq."
                + str(
                    session["client_id"]
                )
        },
        limit=1
    )

    if not rows:

        session.clear()

        flash(
            "Client profile not found."
        )

        return redirect(
            url_for("register")
        )

    client = rows[0]

    if request.method == "POST":

        validate_csrf()

        data = {
            "name":
                clean(
                    request.form.get("name"),
                    150
                ),

            "phone":
                clean(
                    request.form.get("phone"),
                    60
                ),

            "updated_at":
                now_iso(),
        }

        if not data["name"]:

            flash(
                "Name is required."
            )

        else:

            try:

                db_update(
                    "koja_clients",
                    {
                        "id":
                            "eq."
                            + str(
                                session["client_id"]
                            )
                    },
                    data,
                    returning=False
                )

                session["client_name"] = (
                    data["name"]
                )

                flash(
                    "Profile updated successfully."
                )

                return redirect(
                    url_for("profile")
                )

            except Exception as exc:

                logging.exception(
                    "Profile update failed"
                )

                flash(
                    "Profile update error: "
                    + str(exc)[:350]
                )

    body = """
<div class="card">

<h2>My Profile</h2>

<form method="POST">

<input
    type="hidden"
    name="csrf_token"
    value="{{ csrf_token() }}"
>

<label>
Full Name
</label>

<input
    name="name"
    value="{{ client.name or '' }}"
    required
>

<label>
Email
</label>

<input
    value="{{ client.email or '' }}"
    disabled
>

<label>
Phone / Contact
</label>

<input
    name="phone"
    value="{{ client.phone or '' }}"
    required
>

<button type="submit">
Save Profile
</button>

</form>

</div>

<div class="card">

<h3>University Information</h3>

<p>
University information is collected inside
the appropriate KOJA service request rather
than being required for your basic account.
</p>

<a class="btn"
   href="{{ url_for('services') }}">
    Choose a Service
</a>

</div>
"""

    return page(
        "My Profile",
        body,
        client=client
    )


# ============================================================
# CLIENT DASHBOARD
# ============================================================

@app.route("/dashboard")
@client_login_required
def dashboard():

    email = session["client_email"]

    requests_data = db_select(
        "koja_service_requests",
        select="*",
        filters={
            "client_email":
                "eq." + email
        },
        order="created_at.desc",
        limit=100
    )

    unread = db_select(
        "koja_notifications",
        select="id",
        filters={
            "client_email":
                "eq." + email,

            "is_read":
                "eq.false"
        },
        limit=100
    )

    completed_count = sum(
        1
        for r in requests_data
        if r.get("status")
        == STATUS_COMPLETED
    )

    body = """
<div class="card">

<h1>
Welcome,
{{ session.get("client_name") }}
</h1>

<p>
Manage your KOJA requests and receive
completed documents through your account.
</p>

<a class="btn"
   href="{{ url_for('services') }}">
    New KOJA Request
</a>

<a class="btn light"
   href="{{ url_for('my_requests') }}">
    My Requests
</a>

</div>

<div class="stats">

<div class="stat">
Requests
<strong>
{{ requests_data|length }}
</strong>
</div>

<div class="stat">
Unread Notifications
<strong>
{{ unread|length }}
</strong>
</div>

<div class="stat">
Completed
<strong>
{{ completed_count }}
</strong>
</div>

</div>

<div class="card">

<h2>Recent Requests</h2>

{% if requests_data %}

{% for r in requests_data %}

<div class="info-box">

<strong>
{{ r.request_number }}
</strong>

<br>

{{ r.service_type }}

<br><br>

<span class="status {{ status_class(r.status) }}">
{{ client_status_label(r.status) }}
</span>

<br><br>

<a class="btn"
   href="{{ url_for(
       'request_detail',
       request_id=r.id
   ) }}">
    View Request
</a>

</div>

{% endfor %}

{% else %}

<p>
You have not submitted any requests yet.
</p>

<a class="btn"
   href="{{ url_for('services') }}">
    Choose a Service
</a>

{% endif %}

</div>
"""

    return page(
        "Dashboard",
        body,
        requests_data=requests_data,
        unread=unread
    )


# ============================================================
# NEW REQUEST
# ============================================================

@app.route(
    "/request/new",
    methods=["GET", "POST"]
)
@client_login_required
def new_request():

    selected_service = clean(
        request.args.get("service"),
        200
    )

    if (
        selected_service
        and
        selected_service not in PUBLIC_SERVICES
    ):
        abort(404)

    if not selected_service:
        return redirect(
            url_for("services")
        )

    # --------------------------------------------------------
    # LOAD UNIVERSITIES ONLY FOR UNIVERSITY SERVICES
    # --------------------------------------------------------

    universities = []

    if selected_service in UNIVERSITY_SERVICES:

        try:

            universities = db_select(
                "koja_universities",
                select="*",
                filters={
                    "active":
                        "eq.true"
                },
                order="name.asc"
            )

        except Exception as exc:

            logging.exception(
                "University loading failed"
            )

            flash(
                "University list could not "
                "be loaded: "
                + str(exc)[:250]
            )

    # --------------------------------------------------------
    # LOAD CLIENT
    # --------------------------------------------------------

    clients = db_select(
        "koja_clients",
        select="*",
        filters={
            "id":
                "eq."
                + str(
                    session["client_id"]
                )
        },
        limit=1
    )

    client = (
        clients[0]
        if clients
        else {}
    )

    # --------------------------------------------------------
    # POST REQUEST
    # --------------------------------------------------------

    if request.method == "POST":

        validate_csrf()

        service_type = clean(
            request.form.get(
                "service_type"
            ),
            200
        )

        if service_type not in PUBLIC_SERVICES:
            abort(400)

        description = clean(
            request.form.get(
                "description"
            ),
            10000
        )

        supporting_file = (
            request.files.get(
                "supporting_file"
            )
        )

        # ====================================================
        # UNIVERSITY INFORMATION
        # ====================================================

        university = ""
        mode_of_study = ""
        school = ""
        programme = ""
        academic_level = ""
        year_of_study = ""
        student_number = ""

        if service_type in UNIVERSITY_SERVICES:

            university = clean(
                request.form.get(
                    "university"
                ),
                200
            )

            mode_of_study = clean(
                request.form.get(
                    "mode_of_study"
                ),
                80
            )

            school = clean(
                request.form.get(
                    "school"
                ),
                200
            )

            programme = clean(
                request.form.get(
                    "programme"
                ),
                250
            )

            academic_level = clean(
                request.form.get(
                    "academic_level"
                ),
                100
            )

            year_of_study = clean(
                request.form.get(
                    "year_of_study"
                ),
                80
            )

            student_number = clean(
                request.form.get(
                    "student_number"
                ),
                100
            )

        # ====================================================
        # TPN PERSONAL INFORMATION
        # ====================================================

        tpn_information = {}

        if service_type == "TPN Centre":

            tpn_full_name = clean(
                request.form.get(
                    "tpn_full_name"
                ),
                150
            )

            date_of_birth = clean(
                request.form.get(
                    "date_of_birth"
                ),
                30
            )

            nrc_number = clean(
                request.form.get(
                    "nrc_number"
                ),
                80
            )

            tpn_phone = clean(
                request.form.get(
                    "tpn_phone"
                ),
                60
            )

            tpn_email = clean(
                request.form.get(
                    "tpn_email"
                ),
                180
            ).lower()

            house_number = clean(
                request.form.get(
                    "house_number"
                ),
                100
            )

            province = clean(
                request.form.get(
                    "province"
                ),
                100
            )

            district = clean(
                request.form.get(
                    "district"
                ),
                100
            )

            postal_address = clean(
                request.form.get(
                    "postal_address"
                ),
                500
            )

            tpn_information = {
                "full_name":
                    tpn_full_name,

                "date_of_birth":
                    date_of_birth,

                "nrc_number":
                    nrc_number,

                "phone_number":
                    tpn_phone,

                "email":
                    tpn_email,

                "house_number":
                    house_number,

                "province":
                    province,

                "district":
                    district,

                "postal_address":
                    postal_address,
            }

            required_tpn = [
                (
                    "Full name",
                    tpn_full_name
                ),
                (
                    "Date of birth",
                    date_of_birth
                ),
                (
                    "NRC number",
                    nrc_number
                ),
                (
                    "Phone number",
                    tpn_phone
                ),
                (
                    "Email",
                    tpn_email
                ),
                (
                    "House number",
                    house_number
                ),
                (
                    "Province",
                    province
                ),
                (
                    "District",
                    district
                ),
                (
                    "Postal address",
                    postal_address
                ),
            ]

            missing = [
                label
                for label, value
                in required_tpn
                if not value
            ]

            if missing:

                flash(
                    "Please provide: "
                    + ", ".join(missing)
                )

                return redirect(
                    url_for(
                        "new_request",
                        service=service_type
                    )
                )

            # ------------------------------------------------
            # Store TPN personal information inside the
            # existing request description.
            # ------------------------------------------------

            tpn_block = (
                "\n\n"
                "==============================\n"
                "TPN PERSONAL INFORMATION\n"
                "==============================\n"
                f"Full Name: {tpn_full_name}\n"
                f"Date of Birth: {date_of_birth}\n"
                f"NRC Number: {nrc_number}\n"
                f"Phone Number: {tpn_phone}\n"
                f"Email: {tpn_email}\n"
                f"House Number: {house_number}\n"
                f"Province: {province}\n"
                f"District: {district}\n"
                f"Postal Address: {postal_address}\n"
                "==============================\n"
            )

            description = (
                description
                + tpn_block
            )

        # ====================================================
        # GENERAL VALIDATION
        # ====================================================

        if not description.strip():

            flash(
                "Please describe the "
                "request."
            )

            return redirect(
                url_for(
                    "new_request",
                    service=service_type
                )
            )

        if (
            supporting_file
            and
            supporting_file.filename
        ):

            if not allowed_file(
                supporting_file.filename
            ):

                flash(
                    "Unsupported file type."
                )

                return redirect(
                    url_for(
                        "new_request",
                        service=service_type
                    )
                )

        # ====================================================
        # CREATE REQUEST
        # ====================================================

        try:

            request_number = (
                create_unique_request_number()
            )

            created = db_insert(
                "koja_service_requests",
                {
                    "request_number":
                        request_number,

                    "client_id":
                        session["client_id"],

                    "client_name":
                        session["client_name"],

                    "client_email":
                        session["client_email"],

                    "client_phone":
                        client.get(
                            "phone",
                            ""
                        ),

                    "service_type":
                        service_type,

                    "description":
                        description,

                    "university":
                        university,

                    "mode_of_study":
                        mode_of_study,

                    "school":
                        school,

                    "programme":
                        programme,

                    "academic_level":
                        academic_level,

                    "year_of_study":
                        year_of_study,

                    "student_number":
                        student_number,

                    "status":
                        STATUS_NEW,

                    "admin_message":
                        "",

                    "created_at":
                        now_iso(),

                    "updated_at":
                        now_iso(),
                }
            )

            item = created[0]

            request_id = item["id"]

            # =================================================
            # SUPPORTING FILE
            # =================================================

            if (
                supporting_file
                and
                supporting_file.filename
            ):

                upload = storage_upload(
                    supporting_file,
                    folder=(
                        "supporting/"
                        + str(request_id)
                    )
                )

                db_insert(
                    "koja_request_files",
                    {
                        "request_id":
                            request_id,

                        "file_name":
                            upload["file_name"],

                        "file_url":
                            upload["path"],

                        "file_type":
                            upload["content_type"],

                        "file_size":
                            upload["size"],

                        "uploaded_by":
                            session[
                                "client_email"
                            ],

                        "created_at":
                            now_iso(),
                    },
                    returning=False
                )

            # =================================================
            # HISTORY
            # =================================================

            db_insert(
                "koja_request_history",
                {
                    "request_id":
                        request_id,

                    "old_status":
                        None,

                    "new_status":
                        STATUS_NEW,

                    "message":
                        "Request submitted to "
                        "KOJA AFRICA.",

                    "changed_by":
                        session[
                            "client_email"
                        ],

                    "created_at":
                        now_iso(),
                },
                returning=False
            )

            # =================================================
            # NOTIFICATION
            # =================================================

            db_insert(
                "koja_notifications",
                {
                    "client_email":
                        session[
                            "client_email"
                        ],

                    "request_id":
                        request_id,

                    "title":
                        "KOJA Request Received",

                    "message":
                        (
                            "Your KOJA request "
                            + request_number
                            + " has been received. "
                            "KOJA will handle your "
                            "request and update you "
                            "through your account."
                        ),

                    "is_read":
                        False,

                    "created_at":
                        now_iso(),
                },
                returning=False
            )

            flash(
                "Request received successfully. "
                "Reference: "
                + request_number
            )

            return redirect(
                url_for(
                    "request_detail",
                    request_id=request_id
                )
            )

        except Exception as exc:

            logging.exception(
                "Request submission failed"
            )

            flash(
                "Could not submit request: "
                + str(exc)[:400]
            )

    modes = [
        "Full-Time",
        "Part-Time",
        "Distance Learning",
        "Online",
        "Evening",
        "Weekend",
        "Blended",
        "Other",
    ]

    levels = [
        "Certificate",
        "Diploma",
        "Undergraduate",
        "Postgraduate",
        "Masters",
        "PhD",
        "Other",
    ]

    provinces = [
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

    body = """
<div class="card">

<h2>
{{ selected_service }}
</h2>

<p>
{{ description }}
</p>

<div class="info-box">

<strong>
Reference:
</strong>

A request number will automatically be
generated after submission.

</div>

<form
    method="POST"
    enctype="multipart/form-data"
>

<input
    type="hidden"
    name="csrf_token"
    value="{{ csrf_token() }}"
>

<input
    type="hidden"
    name="service_type"
    value="{{ selected_service }}"
>

<label>
Describe the Work / Request *
</label>

<textarea
    name="description"
    required
    placeholder="Explain clearly what you want KOJA to handle..."
></textarea>


{% if selected_service in university_services %}

<div class="card">

<h3 class="section-title">
University Information
</h3>

<p>
University information is requested here because
this service requires academic or university details.
</p>

<label>
University
</label>

<select name="university">

<option value="">
-- Select University --
</option>

{% for university in universities %}

<option value="{{ university.name }}">
{{ university.name }}
</option>

{% endfor %}

</select>

<label>
Mode of Study
</label>

<select name="mode_of_study">

<option value="">
-- Select Mode --
</option>

{% for mode in modes %}

<option value="{{ mode }}">
{{ mode }}
</option>

{% endfor %}

</select>

<label>
School / Faculty
</label>

<input
    name="school"
    placeholder="e.g. School of Natural Sciences"
>

<label>
Programme / Course
</label>

<input
    name="programme"
    placeholder="e.g. Bachelor of Science"
>

<label>
Academic Level
</label>

<select name="academic_level">

<option value="">
-- Select Level --
</option>

{% for level in levels %}

<option value="{{ level }}">
{{ level }}
</option>

{% endfor %}

</select>

<label>
Year of Study
</label>

<input
    name="year_of_study"
    placeholder="e.g. Year 2"
>

<label>
Student Number
</label>

<input
    name="student_number"
    placeholder="University student number"
>

</div>

{% endif %}


{% if selected_service == "TPN Centre" %}

<div class="card">

<h3 class="section-title">
TPN Personal Information
</h3>

<p>
Enter the personal information that should be
sent to the KOJA administrator together with
your TPN request.
</p>

<label>
Full Name *
</label>

<input
    name="tpn_full_name"
    required
    value="{{ client.name or '' }}"
>

<label>
Date of Birth *
</label>

<input
    type="date"
    name="date_of_birth"
    required
>

<label>
NRC Number *
</label>

<input
    name="nrc_number"
    required
    placeholder="Enter NRC number"
>

<label>
Phone Number *
</label>

<input
    name="tpn_phone"
    required
    value="{{ client.phone or '' }}"
    placeholder="e.g. 097xxxxxxx"
>

<label>
Email *
</label>

<input
    type="email"
    name="tpn_email"
    required
    value="{{ client.email or '' }}"
>

<label>
House Number *
</label>

<input
    name="house_number"
    required
    placeholder="e.g. Plot 123"
>

<label>
Province *
</label>

<select
    name="province"
    required
>

<option value="">
-- Select Province --
</option>

{% for province in provinces %}

<option value="{{ province }}">
{{ province }}
</option>

{% endfor %}

</select>

<label>
District *
</label>

<input
    name="district"
    required
    placeholder="Enter district"
>

<label>
Postal Address *
</label>

<textarea
    name="postal_address"
    required
    placeholder="Enter your postal address"
></textarea>

</div>

{% endif %}


<div class="card">

<h3 class="section-title">
Supporting Document
</h3>

<label>
Upload Document
</label>

<input
    type="file"
    name="supporting_file"
>

<p>
Maximum upload size: 25 MB.
</p>

<p>
Supported formats:
PDF, Word, TXT, images, Excel,
PowerPoint and ZIP.
</p>

</div>


<button
    type="submit"
    class="green"
>
Send Request to KOJA
</button>

<a
    class="btn light"
    href="{{ url_for('services') }}"
>
Cancel
</a>

</form>

</div>
"""

    return page(
        "New KOJA Request",
        body,
        selected_service=selected_service,
        description=SERVICE_DESCRIPTIONS.get(
            selected_service,
            ""
        ),
        universities=universities,
        client=client,
        modes=modes,
        levels=levels,
        provinces=provinces,
        university_services=UNIVERSITY_SERVICES
    )


# ============================================================
# MY REQUESTS
# ============================================================

@app.route("/requests")
@client_login_required
def my_requests():

    requests_data = db_select(
        "koja_service_requests",
        select="*",
        filters={
            "client_email":
                "eq."
                + session[
                    "client_email"
                ]
        },
        order="created_at.desc"
    )

    body = """
<div class="card">

<h2>
My KOJA Requests
</h2>

{% if requests_data %}

<table>

<thead>

<tr>
<th>Reference</th>
<th>Service</th>
<th>Status</th>
<th>Date</th>
<th></th>
</tr>

</thead>

<tbody>

{% for r in requests_data %}

<tr>

<td>
<strong>
{{ r.request_number }}
</strong>
</td>

<td>
{{ r.service_type }}
</td>

<td>

<span class="status {{ status_class(r.status) }}">
{{ client_status_label(r.status) }}
</span>

</td>

<td>
{{ r.created_at[:10]
   if r.created_at
   else "" }}
</td>

<td>

<a class="btn"
   href="{{ url_for(
       'request_detail',
       request_id=r.id
   ) }}">
Open
</a>

</td>

</tr>

{% endfor %}

</tbody>

</table>

{% else %}

<p>
No requests found.
</p>

<a class="btn"
   href="{{ url_for('services') }}">
Start a Request
</a>

{% endif %}

</div>
"""

    return page(
        "My Requests",
        body,
        requests_data=requests_data
    )


# ============================================================
# REQUEST DETAIL
# ============================================================

@app.route(
    "/request/<request_id>"
)
@client_login_required
def request_detail(request_id):

    rows = db_select(
        "koja_service_requests",
        select="*",
        filters={
            "id":
                "eq." + request_id,

            "client_email":
                "eq."
                + session[
                    "client_email"
                ]
        },
        limit=1
    )

    if not rows:
        abort(404)

    item = rows[0]

    files = db_select(
        "koja_request_files",
        select="*",
        filters={
            "request_id":
                "eq." + request_id
        },
        order="created_at.asc"
    )

    history = db_select(
        "koja_request_history",
        select="*",
        filters={
            "request_id":
                "eq." + request_id
        },
        order="created_at.desc"
    )

    body = """
<div class="card">

<h2>
{{ item.request_number }}
</h2>

<span class="status {{ status_class(item.status) }}">
{{ client_status_label(item.status) }}
</span>

</div>


<div class="card">

<h3>Client Information</h3>

<p>
<strong>Name:</strong>
{{ item.client_name }}
</p>

<p>
<strong>Email:</strong>
{{ item.client_email }}
</p>

<p>
<strong>Phone:</strong>
{{ item.client_phone }}
</p>

</div>


<div class="card">

<h3>Service</h3>

<p>
<strong>
{{ item.service_type }}
</strong>
</p>

<div class="info-box">
{{ item.description }}
</div>

</div>


{% if item.service_type in university_services %}

<div class="card">

<h3>
University Information
</h3>

<p>
<strong>University:</strong>
{{ item.university or "Not provided" }}
</p>

<p>
<strong>Mode of Study:</strong>
{{ item.mode_of_study or "Not provided" }}
</p>

<p>
<strong>School:</strong>
{{ item.school or "Not provided" }}
</p>

<p>
<strong>Programme:</strong>
{{ item.programme or "Not provided" }}
</p>

<p>
<strong>Academic Level:</strong>
{{ item.academic_level or "Not provided" }}
</p>

<p>
<strong>Year:</strong>
{{ item.year_of_study or "Not provided" }}
</p>

<p>
<strong>Student Number:</strong>
{{ item.student_number or "Not provided" }}
</p>

</div>

{% endif %}


<div class="card">

<h3>
Supporting Documents
</h3>

{% if files %}

{% for f in files %}

<div class="info-box">

<strong>
{{ f.file_name }}
</strong>

<br><br>

<a
    class="btn"
    href="{{ url_for(
        'download_supporting_file',
        file_id=f.id
    ) }}"
>
Download Supporting Document
</a>

</div>

{% endfor %}

{% else %}

<p>
No supporting document uploaded.
</p>

{% endif %}

</div>


{% if item.admin_message %}

<div class="card">

<h3>
Message from KOJA
</h3>

<div class="info-box">
{{ item.admin_message }}
</div>

</div>

{% endif %}


{% if
    item.status == "Completed"
    and
    item.completed_file_url
%}

<div class="card">

<h3>
KOJA Completed Result
</h3>

<p>
<strong>
{{ item.completed_file_name }}
</strong>
</p>

<a
    class="btn green"
    href="{{ url_for(
        'download_completed_file',
        request_id=item.id
    ) }}"
>
Download Your KOJA Result
</a>

</div>

{% endif %}


<div class="card">

<h3>
Request History
</h3>

{% for h in history %}

<div class="info-box">

<strong>
{{ client_status_label(h.new_status) }}
</strong>

<br><br>

{{ h.message or "" }}

<br><br>

<small>
{{ h.created_at or "" }}
</small>

</div>

{% endfor %}

</div>
"""

    return page(
        "Request " + item["request_number"],
        body,
        item=item,
        files=files,
        history=history,
        university_services=UNIVERSITY_SERVICES
    )


# ============================================================
# SUPPORTING FILE DOWNLOAD
# ============================================================

@app.route(
    "/file/supporting/<file_id>"
)
@client_login_required
def download_supporting_file(file_id):

    files = db_select(
        "koja_request_files",
        select="*",
        filters={
            "id":
                "eq." + file_id
        },
        limit=1
    )

    if not files:
        abort(404)

    record = files[0]

    owned = db_select(
        "koja_service_requests",
        select="id",
        filters={
            "id":
                "eq."
                + str(
                    record["request_id"]
                ),

            "client_email":
                "eq."
                + session[
                    "client_email"
                ]
        },
        limit=1
    )

    if not owned:
        abort(403)

    response = storage_download(
        record["file_url"]
    )

    return send_file(
        io.BytesIO(
            response.content
        ),
        mimetype=(
            record.get(
                "file_type"
            )
            or
            "application/octet-stream"
        ),
        as_attachment=True,
        download_name=(
            record["file_name"]
        )
    )


# ============================================================
# COMPLETED FILE DOWNLOAD
# ============================================================

@app.route(
    "/request/<request_id>/download"
)
@client_login_required
def download_completed_file(
    request_id
):

    rows = db_select(
        "koja_service_requests",
        select="*",
        filters={
            "id":
                "eq." + request_id,

            "client_email":
                "eq."
                + session[
                    "client_email"
                ],

            "status":
                "eq."
                + STATUS_COMPLETED
        },
        limit=1
    )

    if not rows:
        abort(404)

    item = rows[0]

    if not item.get(
        "completed_file_url"
    ):
        abort(404)

    response = storage_download(
        item[
            "completed_file_url"
        ]
    )

    return send_file(
        io.BytesIO(
            response.content
        ),
        mimetype=(
            item.get(
                "completed_file_type"
            )
            or
            "application/octet-stream"
        ),
        as_attachment=True,
        download_name=(
            item.get(
                "completed_file_name"
            )
            or
            "KOJA-completed-document"
        )
    )


# ============================================================
# NOTIFICATIONS
# ============================================================

@app.route("/notifications")
@client_login_required
def notifications():

    email = session[
        "client_email"
    ]

    data = db_select(
        "koja_notifications",
        select="*",
        filters={
            "client_email":
                "eq." + email
        },
        order="created_at.desc",
        limit=100
    )

    try:

        db_update(
            "koja_notifications",
            {
                "client_email":
                    "eq." + email,

                "is_read":
                    "eq.false"
            },
            {
                "is_read":
                    True,

                "read_at":
                    now_iso()
            },
            returning=False
        )

    except Exception:

        logging.exception(
            "Notification update failed"
        )

    body = """
<div class="card">

<h2>
Notifications
</h2>

{% if data %}

{% for n in data %}

<div class="info-box">

<strong>
{{ n.title }}
</strong>

<br><br>

{{ n.message }}

<br><br>

<small>
{{ n.created_at or "" }}
</small>

</div>

{% endfor %}

{% else %}

<p>
No notifications.
</p>

{% endif %}

</div>
"""

    return page(
        "Notifications",
        body,
        data=data
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

        validate_csrf()

        username = clean(
            request.form.get(
                "username"
            ),
            100
        )

        password = request.form.get(
            "password",
            ""
        )

        if (
            username == ADMIN_USERNAME
            and
            ADMIN_PASSWORD
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

            session[
                "admin_username"
            ] = username

            session[
                "csrf_token"
            ] = secrets.token_urlsafe(32)

            return redirect(
                url_for(
                    "admin_dashboard"
                )
            )

        flash(
            "Invalid administrator credentials."
        )

    body = """
<div class="card">

<h2>
KOJA AFRICA Administrator
</h2>

<form method="POST">

<input
    type="hidden"
    name="csrf_token"
    value="{{ csrf_token() }}"
>

<label>
Username
</label>

<input
    name="username"
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
Administrator Login
</button>

</form>

</div>
"""

    return page(
        "Administrator",
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

    requests_data = db_select(
        "koja_service_requests",
        select="*",
        order="created_at.desc",
        limit=500
    )

    new_count = sum(
        1
        for r in requests_data
        if r.get("status")
        == STATUS_NEW
    )

    processing_count = sum(
        1
        for r in requests_data
        if r.get("status")
        == STATUS_PROCESSING
    )

    completed_count = sum(
        1
        for r in requests_data
        if r.get("status")
        == STATUS_COMPLETED
    )

    body = """
<div class="card">

<h1>
KOJA AFRICA Admin Dashboard
</h1>

<p>
Manage client requests, supporting documents,
processing status, messages and completed results.
</p>

<a class="btn light"
   href="{{ url_for('admin_logout') }}">
    Logout
</a>

</div>


<div class="stats">

<div class="stat">
New
<strong>
{{ new_count }}
</strong>
</div>

<div class="stat">
Processing
<strong>
{{ processing_count }}
</strong>
</div>

<div class="stat">
Completed
<strong>
{{ completed_count }}
</strong>
</div>

<div class="stat">
Total
<strong>
{{ requests_data|length }}
</strong>
</div>

</div>


<div class="card">

<h2>
Client Requests
</h2>

{% if requests_data %}

<table>

<thead>

<tr>
<th>Reference</th>
<th>Client</th>
<th>Service</th>
<th>Status</th>
<th>Date</th>
<th></th>
</tr>

</thead>

<tbody>

{% for r in requests_data %}

<tr>

<td>
<strong>
{{ r.request_number }}
</strong>
</td>

<td>

{{ r.client_name }}

<br>

<small>
{{ r.client_email }}
</small>

<br>

<small>
{{ r.client_phone }}
</small>

</td>

<td>
{{ r.service_type }}
</td>

<td>

<span class="status {{ status_class(r.status) }}">
{{ r.status }}
</span>

</td>

<td>
{{ r.created_at[:10]
   if r.created_at
   else "" }}
</td>

<td>

<a
    class="btn"
    href="{{ url_for(
        'admin_request',
        request_id=r.id
    ) }}"
>
Open
</a>

</td>

</tr>

{% endfor %}

</tbody>

</table>

{% else %}

<p>
No client requests yet.
</p>

{% endif %}

</div>
"""

    return page(
        "Admin Dashboard",
        body,
        requests_data=requests_data,
        new_count=new_count,
        processing_count=processing_count,
        completed_count=completed_count
    )


# ============================================================
# ADMIN REQUEST
# ============================================================

@app.route(
    "/admin/request/<request_id>",
    methods=["GET", "POST"]
)
@admin_required
def admin_request(request_id):

    rows = db_select(
        "koja_service_requests",
        select="*",
        filters={
            "id":
                "eq." + request_id
        },
        limit=1
    )

    if not rows:
        abort(404)

    item = rows[0]

    files = db_select(
        "koja_request_files",
        select="*",
        filters={
            "request_id":
                "eq." + request_id
        },
        order="created_at.asc"
    )

    if request.method == "POST":

        validate_csrf()

        action = request.form.get(
            "action",
            ""
        )

        message = clean(
            request.form.get(
                "admin_message"
            ),
            10000
        )

        # ====================================================
        # PROCESSING
        # ====================================================

        if action == "processing":

            old_status = item[
                "status"
            ]

            db_update(
                "koja_service_requests",
                {
                    "id":
                        "eq." + request_id
                },
                {
                    "status":
                        STATUS_PROCESSING,

                    "admin_message":
                        message,

                    "updated_at":
                        now_iso()
                },
                returning=False
            )

            db_insert(
                "koja_request_history",
                {
                    "request_id":
                        request_id,

                    "old_status":
                        old_status,

                    "new_status":
                        STATUS_PROCESSING,

                    "message":
                        (
                            message
                            or
                            "KOJA has started "
                            "working on the request."
                        ),

                    "changed_by":
                        session.get(
                            "admin_username",
                            "admin"
                        ),

                    "created_at":
                        now_iso()
                },
                returning=False
            )

            db_insert(
                "koja_notifications",
                {
                    "client_email":
                        item[
                            "client_email"
                        ],

                    "request_id":
                        request_id,

                    "title":
                        "KOJA Is Working on Your Request",

                    "message":
                        (
                            "KOJA is now working "
                            "on your request "
                            + item[
                                "request_number"
                            ]
                            + ". You will be "
                            "notified when it "
                            "is ready."
                        ),

                    "is_read":
                        False,

                    "created_at":
                        now_iso()
                },
                returning=False
            )

            flash(
                "Request marked as Processing."
            )

            return redirect(
                url_for(
                    "admin_request",
                    request_id=request_id
                )
            )

        # ====================================================
        # MESSAGE
        # ====================================================

        if action == "message":

            if not message:

                flash(
                    "Enter a message first."
                )

                return redirect(
                    url_for(
                        "admin_request",
                        request_id=request_id
                    )
                )

            db_update(
                "koja_service_requests",
                {
                    "id":
                        "eq." + request_id
                },
                {
                    "admin_message":
                        message,

                    "updated_at":
                        now_iso()
                },
                returning=False
            )

            db_insert(
                "koja_notifications",
                {
                    "client_email":
                        item[
                            "client_email"
                        ],

                    "request_id":
                        request_id,

                    "title":
                        "Message from KOJA",

                    "message":
                        message,

                    "is_read":
                        False,

                    "created_at":
                        now_iso()
                },
                returning=False
            )

            flash(
                "Message sent to client."
            )

            return redirect(
                url_for(
                    "admin_request",
                    request_id=request_id
                )
            )

        # ====================================================
        # COMPLETE
        # ====================================================

        if action == "complete":

            completed_file = (
                request.files.get(
                    "completed_file"
                )
            )

            if (
                not completed_file
                or
                not completed_file.filename
            ):

                flash(
                    "Please upload the "
                    "completed document."
                )

                return redirect(
                    url_for(
                        "admin_request",
                        request_id=request_id
                    )
                )

            if not allowed_file(
                completed_file.filename
            ):

                flash(
                    "Unsupported completed "
                    "file type."
                )

                return redirect(
                    url_for(
                        "admin_request",
                        request_id=request_id
                    )
                )

            try:

                upload = storage_upload(
                    completed_file,
                    folder=(
                        "completed/"
                        + str(request_id)
                    )
                )

                old_status = item[
                    "status"
                ]

                db_update(
                    "koja_service_requests",
                    {
                        "id":
                            "eq." + request_id
                    },
                    {
                        "status":
                            STATUS_COMPLETED,

                        "admin_message":
                            message,

                        "completed_file_url":
                            upload["path"],

                        "completed_file_name":
                            upload["file_name"],

                        "completed_file_type":
                            upload[
                                "content_type"
                            ],

                        "completed_at":
                            now_iso(),

                        "updated_at":
                            now_iso()
                    },
                    returning=False
                )

                db_insert(
                    "koja_request_history",
                    {
                        "request_id":
                            request_id,

                        "old_status":
                            old_status,

                        "new_status":
                            STATUS_COMPLETED,

                        "message":
                            (
                                message
                                or
                                "KOJA completed "
                                "the request."
                            ),

                        "changed_by":
                            session.get(
                                "admin_username",
                                "admin"
                            ),

                        "created_at":
                            now_iso()
                    },
                    returning=False
                )

                db_insert(
                    "koja_notifications",
                    {
                        "client_email":
                            item[
                                "client_email"
                            ],

                        "request_id":
                            request_id,

                        "title":
                            "Your KOJA Request Is Ready",

                        "message":
                            (
                                "Your KOJA request "
                                + item[
                                    "request_number"
                                ]
                                + " is complete. "
                                "Your finished document "
                                "is now available "
                                "in your account."
                            ),

                        "is_read":
                            False,

                        "created_at":
                            now_iso()
                    },
                    returning=False
                )

                flash(
                    "Request completed successfully."
                )

                return redirect(
                    url_for(
                        "admin_request",
                        request_id=request_id
                    )
                )

            except Exception as exc:

                logging.exception(
                    "Completion failed"
                )

                flash(
                    "Could not complete request: "
                    + str(exc)[:400]
                )

                return redirect(
                    url_for(
                        "admin_request",
                        request_id=request_id
                    )
                )

    body = """
<div class="card">

<h2>
{{ item.request_number }}
</h2>

<span class="status {{ status_class(item.status) }}">
{{ item.status }}
</span>

</div>


<div class="card">

<h3>
Client Information
</h3>

<p>
<strong>Name:</strong>
{{ item.client_name }}
</p>

<p>
<strong>Email:</strong>
{{ item.client_email }}
</p>

<p>
<strong>Phone:</strong>
{{ item.client_phone }}
</p>

</div>


<div class="card">

<h3>
Service
</h3>

<p>
<strong>
{{ item.service_type }}
</strong>
</p>

<div class="info-box">
{{ item.description }}
</div>

</div>


{% if item.service_type == "TPN Centre" %}

<div class="card">

<h3>
TPN Personal Information
</h3>

<div class="info-box">

<p>
The TPN personal information is included in
the request description above and is available
to the administrator for processing.
</p>

<p>
<strong>
Full Name, Date of Birth, NRC, Phone,
Email, House Number, Province, District
and Postal Address
</strong>
are submitted with this request.
</p>

</div>

</div>

{% endif %}


{% if item.service_type in university_services %}

<div class="card">

<h3>
University Information
</h3>

<p>
<strong>University:</strong>
{{ item.university or "Not provided" }}
</p>

<p>
<strong>Mode of Study:</strong>
{{ item.mode_of_study or "Not provided" }}
</p>

<p>
<strong>School:</strong>
{{ item.school or "Not provided" }}
</p>

<p>
<strong>Programme:</strong>
{{ item.programme or "Not provided" }}
</p>

<p>
<strong>Academic Level:</strong>
{{ item.academic_level or "Not provided" }}
</p>

<p>
<strong>Year:</strong>
{{ item.year_of_study or "Not provided" }}
</p>

<p>
<strong>Student Number:</strong>
{{ item.student_number or "Not provided" }}
</p>

</div>

{% endif %}


<div class="card">

<h3>
Supporting Documents
</h3>

{% if files %}

{% for f in files %}

<div class="info-box">

<strong>
{{ f.file_name }}
</strong>

<br>

{{ f.file_type or "" }}

<br><br>

<a
    class="btn"
    href="{{ url_for(
        'admin_download_file',
        file_id=f.id
    ) }}"
>
Download Supporting Document
</a>

</div>

{% endfor %}

{% else %}

<p>
No supporting files.
</p>

{% endif %}

</div>


<div class="card">

<h3>
Move to Processing
</h3>

<form method="POST">

<input
    type="hidden"
    name="csrf_token"
    value="{{ csrf_token() }}"
>

<input
    type="hidden"
    name="action"
    value="processing"
>

<label>
Message to Client
</label>

<textarea
    name="admin_message"
    placeholder="Optional message..."
></textarea>

<button
    class="warning"
    type="submit"
>
Mark Processing
</button>

</form>

</div>


<div class="card">

<h3>
Send Message
</h3>

<form method="POST">

<input
    type="hidden"
    name="csrf_token"
    value="{{ csrf_token() }}"
>

<input
    type="hidden"
    name="action"
    value="message"
>

<label>
Message
</label>

<textarea
    name="admin_message"
    required
></textarea>

<button type="submit">
Send Message
</button>

</form>

</div>


<div class="card">

<h3>
Complete Request
</h3>

<p>
Upload the finished document that the client
should receive.
</p>

<form
    method="POST"
    enctype="multipart/form-data"
>

<input
    type="hidden"
    name="csrf_token"
    value="{{ csrf_token() }}"
>

<input
    type="hidden"
    name="action"
    value="complete"
>

<label>
Finished Document *
</label>

<input
    type="file"
    name="completed_file"
    required
>

<label>
Completion Message
</label>

<textarea
    name="admin_message"
    placeholder="Optional completion message..."
></textarea>

<button
    class="green"
    type="submit"
>
Upload & Mark Completed
</button>

</form>

</div>


{% if
    item.status == "Completed"
    and
    item.completed_file_url
%}

<div class="card">

<h3>
Current Completed File
</h3>

<p>
{{ item.completed_file_name }}
</p>

<a
    class="btn green"
    href="{{ url_for(
        'admin_download_completed',
        request_id=item.id
    ) }}"
>
Download Completed File
</a>

</div>

{% endif %}

"""

    return page(
        "Admin Request",
        body,
        item=item,
        files=files,
        university_services=UNIVERSITY_SERVICES
    )


# ============================================================
# ADMIN SUPPORTING DOWNLOAD
# ============================================================

@app.route(
    "/admin/file/<file_id>"
)
@admin_required
def admin_download_file(file_id):

    files = db_select(
        "koja_request_files",
        select="*",
        filters={
            "id":
                "eq." + file_id
        },
        limit=1
    )

    if not files:
        abort(404)

    record = files[0]

    response = storage_download(
        record["file_url"]
    )

    return send_file(
        io.BytesIO(
            response.content
        ),
        mimetype=(
            record.get(
                "file_type"
            )
            or
            "application/octet-stream"
        ),
        as_attachment=True,
        download_name=(
            record["file_name"]
        )
    )


# ============================================================
# ADMIN COMPLETED DOWNLOAD
# ============================================================

@app.route(
    "/admin/request/<request_id>/completed"
)
@admin_required
def admin_download_completed(
    request_id
):

    rows = db_select(
        "koja_service_requests",
        select="*",
        filters={
            "id":
                "eq." + request_id
        },
        limit=1
    )

    if not rows:
        abort(404)

    item = rows[0]

    if not item.get(
        "completed_file_url"
    ):
        abort(404)

    response = storage_download(
        item[
            "completed_file_url"
        ]
    )

    return send_file(
        io.BytesIO(
            response.content
        ),
        mimetype=(
            item.get(
                "completed_file_type"
            )
            or
            "application/octet-stream"
        ),
        as_attachment=True,
        download_name=(
            item.get(
                "completed_file_name"
            )
            or
            "completed-document"
        )
    )


# ============================================================
# ADMIN HISTORY
# ============================================================

@app.route(
    "/admin/request/<request_id>/history"
)
@admin_required
def admin_history(request_id):

    history = db_select(
        "koja_request_history",
        select="*",
        filters={
            "request_id":
                "eq." + request_id
        },
        order="created_at.desc"
    )

    body = """
<div class="card">

<h2>
Request History
</h2>

{% if history %}

{% for h in history %}

<div class="info-box">

<strong>
{{ h.new_status }}
</strong>

<br><br>

{{ h.message or "" }}

<br><br>

By:
{{ h.changed_by or "System" }}

<br>

{{ h.created_at or "" }}

</div>

{% endfor %}

{% else %}

<p>
No history found.
</p>

{% endif %}

</div>
"""

    return page(
        "Request History",
        body,
        history=history
    )


# ============================================================
# HEALTH
# ============================================================

@app.route("/health")
def health():

    return {
        "status":
            "ok",

        "app":
            APP_NAME,

        "supabase_configured":
            configuration_ok(),

        "time":
            now_iso()
    }


@app.route("/health/database")
def database_health():

    try:

        services = db_select(
            "koja_services",
            select="id,name",
            limit=1
        )

        universities = db_select(
            "koja_universities",
            select="id,name",
            limit=1
        )

        clients = db_select(
            "koja_clients",
            select="id",
            limit=1
        )

        requests_table = db_select(
            "koja_service_requests",
            select="id",
            limit=1
        )

        return {
            "status":
                "ok",

            "database":
                "connected",

            "services_table":
                True,

            "universities_table":
                True,

            "clients_table":
                True,

            "service_requests_table":
                True,

            "sample_services":
                len(services or []),

            "sample_universities":
                len(universities or []),

            "sample_clients":
                len(clients or []),

            "sample_requests":
                len(requests_table or []),
        }

    except Exception as exc:

        logging.exception(
            "Database health check failed"
        )

        return {
            "status":
                "error",

            "database":
                "failed",

            "error":
                str(exc)[:700]
        }, 500


# ============================================================
# ERROR HANDLERS
# ============================================================

@app.errorhandler(413)
def file_too_large(error):

    flash(
        "File is too large. "
        "Maximum allowed size is 25 MB."
    )

    if session.get(
        "admin_logged_in"
    ):

        return redirect(
            url_for(
                "admin_dashboard"
            )
        )

    if session.get(
        "client_id"
    ):

        return redirect(
            url_for("services")
        )

    return redirect(
        url_for("home")
    )


@app.errorhandler(400)
def bad_request(error):

    body = """
<div class="card">

<h1>
400
</h1>

<p>
The request could not be understood.
Please go back and try again.
</p>

<a class="btn"
   href="{{ url_for('home') }}">
    Return Home
</a>

</div>
"""

    return page(
        "Bad Request",
        body
    ), 400


@app.errorhandler(403)
def forbidden(error):

    body = """
<div class="card">

<h1>
403
</h1>

<p>
You are not authorised to access this resource.
</p>

<a class="btn"
   href="{{ url_for('home') }}">
    Return Home
</a>

</div>
"""

    return page(
        "Forbidden",
        body
    ), 403


@app.errorhandler(404)
def not_found(error):

    body = """
<div class="card">

<h1>
404
</h1>

<p>
The requested page or document
was not found.
</p>

<a class="btn"
   href="{{ url_for('home') }}">
    Return Home
</a>

</div>
"""

    return page(
        "Not Found",
        body
    ), 404


@app.errorhandler(500)
def server_error(error):

    logging.exception(
        "Internal server error"
    )

    body = """
<div class="card">

<h1>
Something went wrong
</h1>

<p>
KOJA AFRICA encountered an internal error.
Please try again.
</p>

<a class="btn"
   href="{{ url_for('home') }}">
    Return Home
</a>

</div>
"""

    return page(
        "Server Error",
        body
    ), 500


# ============================================================
# START APPLICATION
# ============================================================

if __name__ == "__main__":

    port = int(
        os.getenv(
            "PORT",
            "10000"
        )
    )

    host = os.getenv(
        "HOST",
        "0.0.0.0"
    )

    logging.info(
        "Starting %s on %s:%s",
        APP_NAME,
        host,
        port
    )

    app.run(
        host=host,
        port=port,
        debug=False
    )

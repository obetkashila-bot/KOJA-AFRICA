import os
import io
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

logging.basicConfig(
    level=logging.INFO
)

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
# KOJA SERVICES
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
        "Submit TPN-related requests and personal "
        "information through KOJA.",

    "Higher Education Materials":
        "Request higher education materials, "
        "academic documents and learning resources.",
}


# ============================================================
# HELPERS
# ============================================================

def configuration_ok():
    return bool(
        SUPABASE_URL
        and SUPABASE_SERVICE_KEY
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
        filename
        .rsplit(".", 1)[1]
        .lower()
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


# ============================================================
# SUPABASE REST API
# ============================================================

def supabase_headers(prefer=None):
    require_configuration()

    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization":
            "Bearer " + SUPABASE_SERVICE_KEY,
        "Content-Type":
            "application/json",
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
            "Supabase error: %s %s %s %s",
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
# STORAGE
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

    try:
        size = (
            request.content_length
            or 0
        )
    except Exception:
        size = 0

    return {
        "path":
            storage_path,

        "file_name":
            original_name,

        "content_type":
            content_type,

        "size":
            size,
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
        "Could not generate a unique request number."
    )


# ============================================================
# AUTH
# ============================================================

def client_login_required(function):

    @wraps(function)
    def wrapper(*args, **kwargs):

        if not session.get("client_id"):

            flash(
                "Please log in or create a KOJA account first."
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
    content="width=device-width, initial-scale=1.0"
>

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

    background: #f3f6fb;
    color: #172033;
}

header {
    background: white;
    border-bottom: 1px solid #e2e7ef;
    padding: 18px;
}

.logo {
    color: #17458f;
    font-size: 30px;
    font-weight: 800;
    margin-bottom: 18px;
}

nav {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
}

nav a {
    text-decoration: none;
    color: #26364f;
    padding: 10px 14px;
    border-radius: 10px;
    font-weight: 600;
}

nav a:hover {
    background: #edf3fc;
}

.container {
    max-width: 1100px;
    margin: auto;
    padding: 25px 18px 60px;
}

.card {
    background: white;
    border-radius: 22px;
    padding: 26px;
    margin-bottom: 22px;
    box-shadow:
        0 8px 30px rgba(30, 50, 80, 0.08);
}

h1 {
    font-size: 34px;
    margin-top: 0;
}

h2 {
    font-size: 27px;
}

h3 {
    font-size: 20px;
}

p {
    line-height: 1.6;
}

label {
    display: block;
    font-weight: 700;
    margin-top: 15px;
    margin-bottom: 7px;
}

input,
select,
textarea {
    width: 100%;
    padding: 13px;
    border: 1px solid #ccd5e3;
    border-radius: 10px;
    font-size: 16px;
    background: white;
}

textarea {
    min-height: 140px;
    resize: vertical;
}

button,
.btn {
    display: inline-block;
    border: none;
    background: #174a96;
    color: white;
    padding: 13px 18px;
    border-radius: 10px;
    font-size: 16px;
    font-weight: 700;
    text-decoration: none;
    cursor: pointer;
    margin-top: 18px;
}

button:hover,
.btn:hover {
    opacity: .9;
}

.btn-secondary {
    background: #5d6b80;
}

.btn-success {
    background: #198754;
}

.btn-warning {
    background: #d98c00;
}

.btn-danger {
    background: #b42318;
}

.hero {
    text-align: center;
    padding: 40px 10px;
}

.hero h1 {
    color: #17458f;
    font-size: 42px;
}

.hero p {
    font-size: 18px;
}

.grid {
    display: grid;
    grid-template-columns:
        repeat(auto-fit, minmax(250px, 1fr));
    gap: 18px;
}

.service-card {
    background: white;
    padding: 22px;
    border-radius: 20px;
    box-shadow:
        0 7px 25px rgba(30,50,80,.08);
}

.service-card h3 {
    color: #17458f;
}

.stat-grid {
    display: grid;
    grid-template-columns:
        repeat(auto-fit, minmax(160px, 1fr));
    gap: 15px;
}

.stat {
    background: white;
    padding: 20px;
    border-radius: 18px;
}

.stat-number {
    font-size: 32px;
    font-weight: 800;
    color: #17458f;
}

.status {
    display: inline-block;
    padding: 8px 13px;
    border-radius: 20px;
    font-weight: 700;
}

.status.new {
    background: #e8f1ff;
    color: #17458f;
}

.status.processing {
    background: #fff1d6;
    color: #9a6200;
}

.status.completed {
    background: #dcf8e8;
    color: #13733d;
}

.alert {
    background: #fff3cd;
    color: #664d03;
    border-radius: 12px;
    padding: 14px;
    margin-bottom: 15px;
}

.info {
    background: #edf5ff;
    border-left: 5px solid #174a96;
    padding: 15px;
    border-radius: 10px;
}

table {
    width: 100%;
    border-collapse: collapse;
}

th,
td {
    padding: 12px;
    border-bottom: 1px solid #e2e7ef;
    text-align: left;
    vertical-align: top;
}

.table-wrap {
    overflow-x: auto;
}

footer {
    text-align: center;
    padding: 40px 20px;
    color: #69758a;
}

.service-icon {
    font-size: 40px;
}

.small {
    color: #69758a;
    font-size: 14px;
}

pre {
    white-space: pre-wrap;
    word-wrap: break-word;
}

@media (max-width: 600px) {

    .container {
        padding: 15px 12px 40px;
    }

    .card {
        padding: 20px;
        border-radius: 17px;
    }

    h1 {
        font-size: 29px;
    }

    .hero h1 {
        font-size: 34px;
    }

    nav {
        gap: 4px;
    }

    nav a {
        padding: 8px 9px;
    }
}

</style>

</head>

<body>

<header>

<div class="logo">
KOJA AFRICA
</div>

<nav>

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

{% if session.get("selected_service") %}
<a href="{{ url_for('new_request') }}">
New Request
</a>
{% endif %}

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

</nav>

</header>

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

<footer>

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

<div class="hero">

<h1>
KOJA AFRICA
</h1>

<h2>
Your Request • KOJA Handles It
</h2>

<p>
KOJA AFRICA is a request-processing platform.
Create an account, choose a service and submit
your request and documents.
</p>

{% if session.get("client_id") %}

<a class="btn"
   href="{{ url_for('services') }}">
    View KOJA Services
</a>

{% else %}

<a class="btn"
   href="{{ url_for('register') }}">
    Get Started
</a>

<a class="btn btn-secondary"
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

<div>
<h3>1. Create Account</h3>
<p>
Create your KOJA client account.
</p>
</div>

<div>
<h3>2. Choose a Service</h3>
<p>
Select the service you need.
</p>
</div>

<div>
<h3>3. Submit</h3>
<p>
Provide the required information
and supporting documents.
</p>
</div>

<div>
<h3>4. Track</h3>
<p>
Follow your request until KOJA
completes it.
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

    try:
        services_data = db_select(
            "koja_services",
            select="*",
            filters={
                "active": "eq.true"
            },
            order="name.asc"
        )
    except Exception:
        logging.exception(
            "Service loading failed"
        )

        services_data = []

    if not services_data:

        services_data = [
            {
                "name": name
            }
            for name in PUBLIC_SERVICES
        ]

    body = """

<div class="card">

<h1>
KOJA Services
</h1>

<p>
Choose the service you need.
</p>

</div>

<div class="grid">

{% for service in services_data %}

<div class="service-card">

<div class="service-icon">

{% if service.name == "Assignments" %}
📚
{% elif service.name == "University Applications" %}
🎓
{% elif service.name == "Result Verification & Certification" %}
📄
{% elif service.name == "Farmer Registration" %}
🧑‍🌾
{% elif service.name == "TPN Centre" %}
📋
{% elif service.name == "Higher Education Materials" %}
📖
{% else %}
📌
{% endif %}

</div>

<h3>
{{ service.name }}
</h3>

<p>
{{ SERVICE_DESCRIPTIONS.get(
    service.name,
    "Submit your request to KOJA."
) }}
</p>

<a class="btn"
   href="{{ url_for(
       'service_start',
       service=service.name
   ) }}">
    Request This Service
</a>

</div>

{% endfor %}

</div>

"""

    return page(
        "KOJA Services",
        body,
        services_data=services_data,
        SERVICE_DESCRIPTIONS=SERVICE_DESCRIPTIONS
    )


# ============================================================
# SERVICE START
# ============================================================

@app.route("/service/<service>")
def service_start(service):

    service = clean(
        service,
        200
    )

    if service not in PUBLIC_SERVICES:

        abort(404)

    session["selected_service"] = service

    if session.get("client_id"):

        return redirect(
            url_for(
                "new_request",
                service=service
            )
        )

    return redirect(
        url_for(
            "register",
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

    selected_service = clean(
        request.args.get("service")
        or session.get(
            "selected_service",
            ""
        ),
        200
    )

    if selected_service not in PUBLIC_SERVICES:
        selected_service = ""

    if selected_service:
        session[
            "selected_service"
        ] = selected_service

    try:

        universities = db_select(
            "koja_universities",
            select="*",
            filters={
                "active": "eq.true"
            },
            order="name.asc"
        )

    except Exception:

        logging.exception(
            "University loading failed"
        )

        universities = []

    if request.method == "POST":

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

            return redirect(
                url_for(
                    "register",
                    service=selected_service
                )
            )

        if not email:
            flash(
                "Email address is required."
            )

            return redirect(
                url_for(
                    "register",
                    service=selected_service
                )
            )

        if not phone:
            flash(
                "Phone/contact is required."
            )

            return redirect(
                url_for(
                    "register",
                    service=selected_service
                )
            )

        if len(password) < 6:

            flash(
                "Password must be at least 6 characters."
            )

            return redirect(
                url_for(
                    "register",
                    service=selected_service
                )
            )

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
                    "An account with that email already exists."
                )

                return redirect(
                    url_for(
                        "login",
                        next_service=selected_service
                    )
                )

            result = db_insert(
                "koja_clients",
                {
                    "name": name,
                    "email": email,
                    "phone": phone,

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

            session[
                "client_id"
            ] = client["id"]

            session[
                "client_name"
            ] = client["name"]

            session[
                "client_email"
            ] = client["email"]

            if selected_service:

                session[
                    "selected_service"
                ] = selected_service

                return redirect(
                    url_for(
                        "new_request",
                        service=selected_service
                    )
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
                + str(exc)[:400]
            )

    body = """

<div class="card">

<h2>
Create KOJA Client Account
</h2>

<p>
Create your account first. After registration,
you will be able to access the KOJA Services.
</p>

{% if selected_service %}

<div class="info">

<strong>
Selected Service:
</strong>

{{ selected_service }}

</div>

{% endif %}

<form method="POST">

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
    autocomplete="tel"
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
        body,
        selected_service=selected_service
    )


# ============================================================
# LOGIN
# ============================================================

@app.route(
    "/login",
    methods=["GET", "POST"]
)
def login():

    next_service = clean(
        request.args.get("next_service")
        or session.get(
            "selected_service",
            ""
        ),
        200
    )

    if next_service not in PUBLIC_SERVICES:
        next_service = ""

    if next_service:
        session[
            "selected_service"
        ] = next_service

    if request.method == "POST":

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
                    url_for(
                        "login",
                        next_service=next_service
                    )
                )

            client = clients[0]

            if not check_password_hash(
                client.get(
                    "password_hash",
                    ""
                ),
                password
            ):

                flash(
                    "Invalid email or password."
                )

                return redirect(
                    url_for(
                        "login",
                        next_service=next_service
                    )
                )

            session.clear()

            session[
                "client_id"
            ] = client["id"]

            session[
                "client_name"
            ] = client.get(
                "name",
                ""
            )

            session[
                "client_email"
            ] = client.get(
                "email",
                ""
            )

            if next_service:

                session[
                    "selected_service"
                ] = next_service

                return redirect(
                    url_for(
                        "new_request",
                        service=next_service
                    )
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
                + str(exc)[:400]
            )

    body = """

<div class="card">

<h2>
KOJA Client Login
</h2>

{% if next_service %}

<div class="info">

You are continuing with:

<strong>
{{ next_service }}
</strong>

</div>

{% endif %}

<form method="POST">

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

<a href="{{ url_for(
    'register',
    service=next_service
) }}">
Create one
</a>
</p>

</div>

"""

    return page(
        "Client Login",
        body,
        next_service=next_service
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

            return redirect(
                url_for("profile")
            )

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

            session[
                "client_name"
            ] = data["name"]

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

<h2>
My Profile
</h2>

<form method="POST">

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

    email = session[
        "client_email"
    ]

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
Manage your KOJA requests and documents.
</p>

<a class="btn"
   href="{{ url_for('services') }}">
    KOJA Services
</a>

</div>

<div class="stat-grid">

<div class="stat">

<div>
Total Requests
</div>

<div class="stat-number">
{{ requests_data|length }}
</div>

</div>

<div class="stat">

<div>
Unread Notifications
</div>

<div class="stat-number">
{{ unread|length }}
</div>

</div>

<div class="stat">

<div>
Completed
</div>

<div class="stat-number">
{{ completed_count }}
</div>

</div>

</div>

<div class="card">

<h2>
Recent Requests
</h2>

{% if requests_data %}

{% for r in requests_data %}

<div class="card">

<strong>
{{ r.request_number }}
</strong>

<p>
{{ r.service_type }}
</p>

<span class="status {{ status_class(r.status) }}">
{{ client_status_label(r.status) }}
</span>

<br>

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
        unread=unread,
        client_status_label=client_status_label,
        status_class=status_class
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
        request.args.get("service")
        or session.get(
            "selected_service",
            ""
        ),
        200
    )

    if selected_service not in PUBLIC_SERVICES:
        selected_service = ""

    if selected_service:
        session[
            "selected_service"
        ] = selected_service

    try:

        services_data = db_select(
            "koja_services",
            select="*",
            filters={
                "active": "eq.true"
            },
            order="name.asc"
        )

    except Exception:

        logging.exception(
            "Service loading failed"
        )

        services_data = []

    if not services_data:

        services_data = [
            {
                "name": s
            }
            for s in PUBLIC_SERVICES
        ]

    try:

        universities = db_select(
            "koja_universities",
            select="*",
            filters={
                "active": "eq.true"
            },
            order="name.asc"
        )

    except Exception:

        logging.exception(
            "University loading failed"
        )

        universities = []

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

    if request.method == "POST":

        service_type = clean(
            request.form.get(
                "service_type"
            ),
            200
        )

        description = clean(
            request.form.get(
                "description"
            ),
            10000
        )

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

        tpn_house_number = clean(
            request.form.get(
                "tpn_house_number"
            ),
            100
        )

        tpn_province = clean(
            request.form.get(
                "tpn_province"
            ),
            100
        )

        tpn_district = clean(
            request.form.get(
                "tpn_district"
            ),
            150
        )

        tpn_date_of_birth = clean(
            request.form.get(
                "tpn_date_of_birth"
            ),
            20
        )

        tpn_nrc_number = clean(
            request.form.get(
                "tpn_nrc_number"
            ),
            100
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

        tpn_postal_address = clean(
            request.form.get(
                "tpn_postal_address"
            ),
            500
        )

        supporting_file = (
            request.files.get(
                "supporting_file"
            )
        )

        # ====================================================
        # VALIDATION
        # ====================================================

        if service_type not in PUBLIC_SERVICES:

            flash(
                "Please select a valid KOJA service."
            )

            return redirect(
                url_for(
                    "new_request",
                    service=selected_service
                )
            )

        if not description:

            flash(
                "Please describe the request."
            )

            return redirect(
                url_for(
                    "new_request",
                    service=service_type
                )
            )

        # ====================================================
        # TPN VALIDATION
        # ====================================================

        if service_type == "TPN Centre":

            if not tpn_house_number:
                flash(
                    "House number is required for TPN requests."
                )
                return redirect(
                    url_for(
                        "new_request",
                        service=service_type
                    )
                )

            if not tpn_province:
                flash(
                    "Province is required for TPN requests."
                )
                return redirect(
                    url_for(
                        "new_request",
                        service=service_type
                    )
                )

            if not tpn_district:
                flash(
                    "District is required for TPN requests."
                )
                return redirect(
                    url_for(
                        "new_request",
                        service=service_type
                    )
                )

            if not tpn_date_of_birth:
                flash(
                    "Date of birth is required for TPN requests."
                )
                return redirect(
                    url_for(
                        "new_request",
                        service=service_type
                    )
                )

            if not tpn_nrc_number:
                flash(
                    "NRC number is required for TPN requests."
                )
                return redirect(
                    url_for(
                        "new_request",
                        service=service_type
                    )
                )

            if not tpn_phone:
                flash(
                    "Phone number is required for TPN requests."
                )
                return redirect(
                    url_for(
                        "new_request",
                        service=service_type
                    )
                )

            if not tpn_email:
                flash(
                    "Email is required for TPN requests."
                )
                return redirect(
                    url_for(
                        "new_request",
                        service=service_type
                    )
                )

            if not tpn_postal_address:
                flash(
                    "Postal address is required for TPN requests."
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

        try:

            request_number = (
                create_unique_request_number()
            )

            request_data = {

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

            # =================================================
            # ADD TPN DATA ONLY FOR TPN
            # =================================================

            if service_type == "TPN Centre":

                request_data.update({

                    "tpn_house_number":
                        tpn_house_number,

                    "tpn_province":
                        tpn_province,

                    "tpn_district":
                        tpn_district,

                    "tpn_date_of_birth":
                        tpn_date_of_birth,

                    "tpn_nrc_number":
                        tpn_nrc_number,

                    "tpn_phone":
                        tpn_phone,

                    "tpn_email":
                        tpn_email,

                    "tpn_postal_address":
                        tpn_postal_address,
                })

            created = db_insert(
                "koja_service_requests",
                request_data
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
                            session["client_email"],

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
                        "Request submitted to KOJA AFRICA.",

                    "changed_by":
                        session["client_email"],

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
                        session["client_email"],

                    "request_id":
                        request_id,

                    "title":
                        "KOJA Request Received",

                    "message":
                        (
                            "Your KOJA request "
                            + request_number
                            + " has been received. "
                            "KOJA will handle your request "
                            "and update you through your account."
                        ),

                    "is_read":
                        False,

                    "created_at":
                        now_iso(),
                },
                returning=False
            )

            session.pop(
                "selected_service",
                None
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
                + str(exc)[:500]
            )

    modes = [
        "Full-Time",
        "Part-Time",
        "Distance Learning",
        "Online",
        "Evening",
        "Weekend",
        "Blended",
        "Other"
    ]

    levels = [
        "Certificate",
        "Diploma",
        "Undergraduate",
        "Postgraduate",
        "Masters",
        "PhD",
        "Other"
    ]

    body = """

<div class="card">

<h2>
Start a KOJA Request
</h2>

<p>
Tell KOJA what you need and provide the information
and documents required.
</p>

{% if selected_service %}

<div class="info">

<strong>
Selected KOJA Service:
</strong>

{{ selected_service }}

</div>

{% endif %}

<form
    method="POST"
    enctype="multipart/form-data"
>

<label>
Service *
</label>

<select name="service_type" required>

<option value="">
-- Select Service --
</option>

{% for service in services_data %}

<option
    value="{{ service.name }}"
    {% if service.name == selected_service %}
        selected
    {% endif %}
>
{{ service.name }}
</option>

{% endfor %}

</select>

<label>
Describe the Work / Request *
</label>

<textarea
    name="description"
    required
    placeholder="Explain what you need KOJA to handle..."
></textarea>


{% if selected_service == "TPN Centre" %}

<div class="card">

<h2>
TPN Personal Information
</h2>

<p>
Please provide the personal information that KOJA
will send to the administrator for processing.
</p>

<label>
Full Name
</label>

<input
    value="{{ client.name or '' }}"
    disabled
>

<label>
House Number *
</label>

<input
    name="tpn_house_number"
    placeholder="House number"
>

<label>
Province *
</label>

<input
    name="tpn_province"
    placeholder="Province"
>

<label>
District *
</label>

<input
    name="tpn_district"
    placeholder="District"
>

<label>
Date of Birth *
</label>

<input
    type="date"
    name="tpn_date_of_birth"
>

<label>
NRC Number *
</label>

<input
    name="tpn_nrc_number"
    placeholder="NRC number"
>

<label>
Phone Number *
</label>

<input
    name="tpn_phone"
    value="{{ client.phone or '' }}"
    placeholder="Phone number"
>

<label>
Email *
</label>

<input
    type="email"
    name="tpn_email"
    value="{{ client.email or '' }}"
    placeholder="Email address"
>

<label>
Postal Address *
</label>

<textarea
    name="tpn_postal_address"
    placeholder="Enter postal address"
></textarea>

</div>

{% endif %}


{% if selected_service == "University Applications"
   or selected_service == "Assignments"
   or selected_service == "Result Verification & Certification"
   or selected_service == "Higher Education Materials" %}

<div class="card">

<h2>
University Information
</h2>

<p>
University information is requested only when
the service requires it.
</p>

<label>
University
</label>

<select name="university">

<option value="">
-- Select University --
</option>

{% for university in universities %}

<option
    value="{{ university.name }}"
>
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


<div class="card">

<h2>
Supporting Document
</h2>

<input
    type="file"
    name="supporting_file"
>

<p class="small">
Maximum upload size: 25 MB.
</p>

<p class="small">
Supported formats:
PDF, Word, TXT, images, Excel,
PowerPoint and ZIP.
</p>

</div>

<button type="submit">
Send Request to KOJA
</button>

</form>

</div>

"""

    return page(
        "New Request",
        body,
        services_data=services_data,
        universities=universities,
        client=client,
        modes=modes,
        levels=levels,
        selected_service=selected_service
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
                + session["client_email"]
        },
        order="created_at.desc"
    )

    body = """

<div class="card">

<h2>
My KOJA Requests
</h2>

{% if requests_data %}

<div class="table-wrap">

<table>

<thead>

<tr>

<th>
Reference
</th>

<th>
Service
</th>

<th>
Status
</th>

<th>
Date
</th>

<th>
</th>

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
   else '' }}
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

</div>

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
        requests_data=requests_data,
        status_class=status_class,
        client_status_label=client_status_label
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
                "eq." + str(request_id),

            "client_email":
                "eq."
                + session["client_email"]
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
                "eq." + str(request_id)
        },
        order="created_at.asc"
    )

    history = db_select(
        "koja_request_history",
        select="*",
        filters={
            "request_id":
                "eq." + str(request_id)
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

<h2>
Client Information
</h2>

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

<h2>
Service
</h2>

<h3>
{{ item.service_type }}
</h3>

<div class="info">
{{ item.description }}
</div>

</div>


{% if item.service_type == "TPN Centre" %}

<div class="card">

<h2>
TPN Personal Information
</h2>

<p>
<strong>House Number:</strong>
{{ item.tpn_house_number or "Not provided" }}
</p>

<p>
<strong>Province:</strong>
{{ item.tpn_province or "Not provided" }}
</p>

<p>
<strong>District:</strong>
{{ item.tpn_district or "Not provided" }}
</p>

<p>
<strong>Date of Birth:</strong>
{{ item.tpn_date_of_birth or "Not provided" }}
</p>

<p>
<strong>NRC Number:</strong>
{{ item.tpn_nrc_number or "Not provided" }}
</p>

<p>
<strong>Phone:</strong>
{{ item.tpn_phone or "Not provided" }}
</p>

<p>
<strong>Email:</strong>
{{ item.tpn_email or "Not provided" }}
</p>

<p>
<strong>Postal Address:</strong>
{{ item.tpn_postal_address or "Not provided" }}
</p>

</div>

{% endif %}


{% if item.university
   or item.school
   or item.programme
   or item.student_number %}

<div class="card">

<h2>
University Information
</h2>

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

<h2>
Supporting Documents
</h2>

{% if files %}

{% for f in files %}

<p>
<strong>
{{ f.file_name }}
</strong>
</p>

<a class="btn"
   href="{{ url_for(
       'download_supporting_file',
       file_id=f.id
   ) }}">
    Download Supporting Document
</a>

<hr>

{% endfor %}

{% else %}

<p>
No supporting document uploaded.
</p>

{% endif %}

</div>


{% if item.admin_message %}

<div class="card">

<h2>
Message from KOJA
</h2>

<div class="info">
{{ item.admin_message }}
</div>

</div>

{% endif %}


{% if item.status == "Completed"
   and item.completed_file_url %}

<div class="card">

<h2>
KOJA Completed Result
</h2>

<p>
<strong>
{{ item.completed_file_name }}
</strong>
</p>

<a class="btn btn-success"
   href="{{ url_for(
       'download_completed_file',
       request_id=item.id
   ) }}">
    Download Your KOJA Result
</a>

</div>

{% endif %}


<div class="card">

<h2>
Request History
</h2>

{% for h in history %}

<div>

<strong>
{{ client_status_label(h.new_status) }}
</strong>

<p>
{{ h.message or "" }}
</p>

<p class="small">
{{ h.created_at or "" }}
</p>

<hr>

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
        client_status_label=client_status_label,
        status_class=status_class
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
                "eq." + str(file_id)
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
                + str(record["request_id"]),

            "client_email":
                "eq."
                + session["client_email"]
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
            record.get("file_type")
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
                "eq." + str(request_id),

            "client_email":
                "eq."
                + session["client_email"],

            "status":
                "eq." + STATUS_COMPLETED
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
        item["completed_file_url"]
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

<div class="card">

<h3>
{{ n.title }}
</h3>

<p>
{{ n.message }}
</p>

<p class="small">
{{ n.created_at or "" }}
</p>

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
            and ADMIN_PASSWORD
            and secrets.compare_digest(
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

<p>
This is the separate administrator login.
It is not the client login.
</p>

<form
    method="POST"
    action="{{ url_for('admin_login') }}"
>

<label>
Username
</label>

<input
    type="text"
    name="username"
    required
    autocomplete="username"
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
Administrator Login
</button>

</form>

</div>

"""

    return page(
        "Administrator Login",
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
Welcome,
<strong>
{{ session.get("admin_username") }}
</strong>
</p>

<p>
Manage client requests, TPN information,
documents, messages and completed results.
</p>

<a class="btn btn-danger"
   href="{{ url_for('admin_logout') }}">
    Admin Logout
</a>

</div>


<div class="stat-grid">

<div class="stat">

<div>
New
</div>

<div class="stat-number">
{{ new_count }}
</div>

</div>

<div class="stat">

<div>
Processing
</div>

<div class="stat-number">
{{ processing_count }}
</div>

</div>

<div class="stat">

<div>
Completed
</div>

<div class="stat-number">
{{ completed_count }}
</div>

</div>

<div class="stat">

<div>
Total
</div>

<div class="stat-number">
{{ requests_data|length }}
</div>

</div>

</div>


<div class="card">

<h2>
Client Requests
</h2>

<div class="table-wrap">

<table>

<thead>

<tr>

<th>
Reference
</th>

<th>
Client
</th>

<th>
Service
</th>

<th>
Status
</th>

<th>
Date
</th>

<th>
</th>

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

<span class="small">
{{ r.client_email }}
</span>

<br>

<span class="small">
{{ r.client_phone }}
</span>

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

<a class="btn"
   href="{{ url_for(
       'admin_request',
       request_id=r.id
   ) }}">
    Open
</a>

</td>

</tr>

{% endfor %}

</tbody>

</table>

</div>

</div>

"""

    return page(
        "Admin Dashboard",
        body,
        requests_data=requests_data,
        new_count=new_count,
        processing_count=processing_count,
        completed_count=completed_count,
        status_class=status_class
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
                "eq." + str(request_id)
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
                "eq." + str(request_id)
        },
        order="created_at.asc"
    )

    if request.method == "POST":

        action = clean(
            request.form.get(
                "action"
            ),
            50
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

            old_status = item.get(
                "status"
            )

            db_update(
                "koja_service_requests",
                {
                    "id":
                        "eq."
                        + str(request_id)
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
                            "KOJA has started working on the request."
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
                        item["client_email"],

                    "request_id":
                        request_id,

                    "title":
                        "KOJA Is Working on Your Request",

                    "message":
                        (
                            "KOJA is now working on your request "
                            + item["request_number"]
                            + ". You will be notified "
                            "when it is ready."
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
                        "eq."
                        + str(request_id)
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
                        item["client_email"],

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
                    "Please upload the completed document."
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
                    "Unsupported completed file type."
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

                old_status = item.get(
                    "status"
                )

                db_update(
                    "koja_service_requests",
                    {
                        "id":
                            "eq."
                            + str(request_id)
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
                            upload["content_type"],

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
                                "KOJA completed the request."
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
                            item["client_email"],

                        "request_id":
                            request_id,

                        "title":
                            "Your KOJA Request Is Ready",

                        "message":
                            (
                                "Your KOJA request "
                                + item["request_number"]
                                + " is complete. "
                                "Your finished document "
                                "is now available in your account."
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

<h2>
Client Information
</h2>

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

<h2>
Service
</h2>

<h3>
{{ item.service_type }}
</h3>

<div class="info">
{{ item.description }}
</div>

</div>


{% if item.service_type == "TPN Centre" %}

<div class="card">

<h2>
TPN Personal Information
</h2>

<p>
<strong>House Number:</strong>
{{ item.tpn_house_number or "Not provided" }}
</p>

<p>
<strong>Province:</strong>
{{ item.tpn_province or "Not provided" }}
</p>

<p>
<strong>District:</strong>
{{ item.tpn_district or "Not provided" }}
</p>

<p>
<strong>Date of Birth:</strong>
{{ item.tpn_date_of_birth or "Not provided" }}
</p>

<p>
<strong>NRC Number:</strong>
{{ item.tpn_nrc_number or "Not provided" }}
</p>

<p>
<strong>Phone:</strong>
{{ item.tpn_phone or "Not provided" }}
</p>

<p>
<strong>Email:</strong>
{{ item.tpn_email or "Not provided" }}
</p>

<p>
<strong>Postal Address:</strong>
{{ item.tpn_postal_address or "Not provided" }}
</p>

</div>

{% endif %}


{% if item.university
   or item.school
   or item.programme
   or item.student_number %}

<div class="card">

<h2>
University Information
</h2>

<p>
<strong>University:</strong>
{{ item.university or "Not provided" }}
</p>

<p>
<strong>Mode:</strong>
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

{% endif %}

</div>


<div class="card">

<h2>
Supporting Documents
</h2>

{% if files %}

{% for f in files %}

<p>
<strong>
{{ f.file_name }}
</strong>
</p>

<a class="btn"
   href="{{ url_for(
       'admin_download_file',
       file_id=f.id
   ) }}">
    Download Supporting Document
</a>

<hr>

{% endfor %}

{% else %}

<p>
No supporting files.
</p>

{% endif %}

</div>


<div class="card">

<h2>
Move to Processing
</h2>

<form
    method="POST"
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
    class="btn-warning"
    type="submit"
>
Mark Processing
</button>

</form>

</div>


<div class="card">

<h2>
Send Message
</h2>

<form
    method="POST"
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
    placeholder="Write a message to the client..."
></textarea>

<button type="submit">
Send Message
</button>

</form>

</div>


<div class="card">

<h2>
Complete Request
</h2>

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
    class="btn-success"
    type="submit"
>
Upload & Mark Completed
</button>

</form>

</div>


{% if item.status == "Completed"
   and item.completed_file_url %}

<div class="card">

<h2>
Current Completed File
</h2>

<p>
{{ item.completed_file_name }}
</p>

<a class="btn btn-success"
   href="{{ url_for(
       'admin_download_completed',
       request_id=item.id
   ) }}">
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
        status_class=status_class
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
                "eq." + str(file_id)
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
            record.get("file_type")
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
                "eq." + str(request_id)
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
        item["completed_file_url"]
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
                "eq." + str(request_id)
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

<div class="card">

<strong>
{{ h.new_status }}
</strong>

<p>
{{ h.message or "" }}
</p>

<p>
By:
{{ h.changed_by or "System" }}
</p>

<p class="small">
{{ h.created_at or "" }}
</p>

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

        return {

            "status":
                "ok",

            "database":
                "connected",

            "services_table":
                True,

            "universities_table":
                True,

            "sample_services":
                len(services or []),

            "sample_universities":
                len(universities or [])
        }

    except Exception as exc:

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

@app.errorhandler(400)
def bad_request(error):

    logging.error(
        "400 Bad Request: %s",
        error
    )

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


@app.errorhandler(413)
def file_too_large(error):

    flash(
        "File is too large. Maximum allowed size is 25 MB."
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
            url_for(
                "services"
            )
        )

    return redirect(
        url_for("home")
    )


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
